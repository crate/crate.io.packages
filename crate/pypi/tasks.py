import collections
import datetime
import hashlib
import logging
import re
import socket
import time
import xmlrpclib

import redis
import requests

from celery.task import task

from django.conf import settings
from django.db import transaction
from django.utils.timezone import now

from crate.pypi.utils.lock import Lock
from crate.web.packages.models import Package, ReleaseFile, TroveClassifier, DownloadDelta
from crate.pypi.models import PyPIIndexPage, PyPIDownloadChange
from crate.pypi.processor import PyPIPackage

logger = logging.getLogger(__name__)

INDEX_URL = "http://pypi.python.org/pypi"

CLASSIFIER_URL = "http://pypi.python.org/pypi?%3Aaction=list_classifiers"

PYPI_SINCE_KEY = "crate:pypi:since"


def process(name, version, timestamp, action, matches):
    package = PyPIPackage(name, version)
    package.process()


def remove(name, version, timestamp, action, matches):
    package = PyPIPackage(name, version)
    package.delete()


def remove_file(name, version, timestamp, action, matches):
    package = PyPIPackage(name, version)
    package.remove_files(*matches.groups())


@task
def bulk_process(name, version, timestamp, action, matches):
    package = PyPIPackage(name)
    package.process(bulk=True)


@task
def bulk_synchronize():
    pypi = xmlrpclib.ServerProxy(INDEX_URL)

    names = set()

    for package in pypi.list_packages():
        names.add(package)
        bulk_process.delay(package, None, None, None, None)

    for package in Package.objects.exclude(name__in=names):
        package.delete()


@task
def synchronize(since=None):
    with Lock("synchronize", expires=60 * 5, timeout=30):
        datastore = redis.StrictRedis(**dict([(x.lower(), y) for x, y in settings.REDIS[settings.PYPI_DATASTORE].items()]))

        if since is None:
            s = datastore.get(PYPI_SINCE_KEY)
            if s is not None:
                since = int(float(s)) - 30

        current = time.mktime(datetime.datetime.utcnow().timetuple())

        pypi = xmlrpclib.ServerProxy(INDEX_URL)

        if since is None:  # @@@ Should we do this for more than just initial?
            bulk_synchronize.delay()
        else:
            logger.info("[SYNCING] Changes since %s" % since)
            changes = pypi.changelog(since)

            for name, version, timestamp, action in changes:
                line_hash = hashlib.sha256(u":".join([unicode(x) for x in (name, version, timestamp, action)]).encode("utf-8")).hexdigest()
                logdata = {"action": action, "name": name, "version": version, "timestamp": timestamp, "hash": line_hash}

                if not datastore.exists("crate:pypi:changelog:%s" % line_hash):
                    logger.debug("[PROCESS] %(name)s %(version)s %(timestamp)s %(action)s" % logdata)
                    logger.debug("[HASH] %(name)s %(version)s %(hash)s" % logdata)

                    dispatch = collections.OrderedDict([
                        (re.compile("^create$"), process),
                        (re.compile("^new release$"), process),
                        (re.compile("^add [\w\d\.]+ file .+$"), process),
                        (re.compile("^remove$"), remove),
                        (re.compile("^remove file (.+)$"), remove_file),
                        (re.compile("^update [\w]+(, [\w]+)*$"), process),
                        #(re.compile("^docupdate$"), docupdate),  # @@@ Do Something
                        #(re.compile("^add (Owner|Maintainer) .+$"), add_user_role),  # @@@ Do Something
                        #(re.compile("^remove (Owner|Maintainer) .+$"), remove_user_role),  # @@@ Do Something
                    ])

                    # Dispatch Based on the action
                    for pattern, func in dispatch.iteritems():
                        matches = pattern.search(action)
                        if matches is not None:
                            func(name, version, timestamp, action, matches)
                            break
                    else:
                        logger.warn("[UNHANDLED] %(name)s %(version)s %(timestamp)s %(action)s" % logdata)

                    datastore.setex("crate:pypi:changelog:%s" % line_hash, 2629743, datetime.datetime.utcnow().isoformat())
                else:
                    logger.debug("[SKIP] %(name)s %(version)s %(timestamp)s %(action)s" % logdata)
                    logger.debug("[HASH] %(name)s %(version)s %(hash)s" % logdata)

        datastore.set(PYPI_SINCE_KEY, current)


@task
def synchronize_troves():
    resp = requests.get(CLASSIFIER_URL)
    resp.raise_for_status()

    current_troves = set(TroveClassifier.objects.all().values_list("trove", flat=True))
    new_troves = set([x.strip() for x in resp.content.splitlines()]) - current_troves

    with transaction.commit_on_success():
        for classifier in new_troves:
            TroveClassifier.objects.get_or_create(trove=classifier)


@task
def synchronize_downloads():
    for package in Package.objects.all().order_by("downloads_synced_on").prefetch_related("releases", "releases__files")[:150]:
        Package.objects.filter(pk=package.pk).update(downloads_synced_on=now())

        for release in package.releases.all():
            update_download_counts.delay(package.name, release.version, dict([(x.filename, x.pk) for x in release.files.all()]))


@task
def update_download_counts(package_name, version, files, index=None):
    try:
        pypi = xmlrpclib.ServerProxy(INDEX_URL)

        downloads = pypi.release_downloads(package_name, version)

        for filename, download_count in downloads:
            if filename in files:
                with transaction.commit_on_success():
                    for releasefile in ReleaseFile.objects.filter(pk=files[filename]).select_for_update():
                        old = releasefile.downloads
                        releasefile.downloads = download_count
                        releasefile.save()

                        change = releasefile.downloads - old
                        if change:
                            PyPIDownloadChange.objects.create(file=releasefile, change=change)
    except socket.error:
        logger.exception("[DOWNLOAD SYNC] Network Error")


@task
def refresh_pypi_package_index_cache():
    r = requests.get("http://pypi.python.org/simple/", prefetch=True)
    PyPIIndexPage.objects.create(content=r.content)


@task
def integrate_download_deltas():
    with Lock("pypi-integrate-downloads", expires=60 * 5, timeout=30):
        count = 0

        for d in PyPIDownloadChange.objects.filter(integrated=False)[:1000]:
            with transaction.commit_on_success():
                dd, c = DownloadDelta.objects.get_or_create(file=d.file, date=d.created.date(), defaults={"delta": d.change})

                if not c:
                    DownloadDelta.objects.filter(pk=dd.pk).select_for_update()

                    dd.delta += d.change
                    dd.save()

                PyPIDownloadChange.objects.filter(pk=d.pk).update(integrated=True)
            count += 1

        return count
