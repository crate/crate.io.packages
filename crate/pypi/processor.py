import base64
import hashlib
import logging
import re
import urllib
import urlparse
import xmlrpclib

import redis
import requests
import lxml.html

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.timezone import utc

from crate.web.history.models import Event
from crate.web.packages.models import Package, Release, TroveClassifier
from crate.web.packages.models import ReleaseRequire, ReleaseProvide, ReleaseObsolete, ReleaseURI, ReleaseFile
from crate.pypi.exceptions import PackageHashMismatch
from crate.pypi.models import PyPIMirrorPage

logger = logging.getLogger(__name__)

INDEX_URL = "http://pypi.python.org/pypi"
SIMPLE_URL = "http://pypi.python.org/simple/"

_disutils2_version_capture = re.compile("^(.*?)(?:\(([^()]+)\))?$")
_md5_re = re.compile(r"(https?://pypi\.python\.org/packages/.+)#md5=([a-f0-9]+)")


def get_helper(data, key, default=None):
    if data.get(key) and data[key] != "UNKNOWN":
        return data[key]
    return "" if default is None else default


def split_meta(meta):
    meta_split = meta.split(";", 1)
    meta_name, meta_version = _disutils2_version_capture.search(meta_split[0].strip()).groups()
    meta_env = meta_split[1].strip() if len(meta_split) == 2 else ""

    return {
        "name": meta_name,
        "version": meta_version if meta_version is not None else "",
        "environment": meta_env,
    }


class PyPIPackage(object):

    def __init__(self, name, version=None):
        self.name = name
        self.version = version

        self.stored = False

        self.pypi = xmlrpclib.ServerProxy(INDEX_URL, use_datetime=True)
        self.datastore = redis.StrictRedis(**dict([(x.lower(), y) for x, y in settings.REDIS[settings.PYPI_DATASTORE].items()]))

    def process(self, bulk=False, download=True, skip_modified=True):
        self.bulk = bulk
        self.skip_modified = skip_modified

        self.fetch()
        self.build()

        with transaction.commit_on_success():
            self.store()

            # do not download package files
            #if download:
            #    self.download()

    def delete(self):
        with transaction.commit_on_success():
            self.verify_and_sync_pages()

            if self.version is None:
                # Delete the entire package
                packages = Package.objects.filter(name=self.name).select_for_update()
                releases = Release.objects.filter(package__in=packages).select_for_update()

                for package in packages:
                    package.delete()
            else:
                # Delete only this release
                try:
                    package = Package.objects.get(name=self.name)
                except Package.DoesNotExist:
                    return

                releases = Release.objects.filter(package=package, version=self.version).select_for_update()

                for release in releases:
                    release.hidden = True
                    release.save()

    def remove_files(self, *files):
        self.verify_and_sync_pages()

        packages = Package.objects.filter(name=self.name)
        releases = Release.objects.filter(package__in=packages)

        for rf in ReleaseFile.objects.filter(release__in=releases, filename__in=files):
            rf.hidden = True
            rf.save()

    def fetch(self):
        logger.debug("[FETCH] %s%s" % (self.name, " %s" % self.version if self.version else ""))

        # Fetch meta data for this release
        self.releases = self.get_releases()
        self.release_data = self.get_release_data()
        self.release_url_data = self.get_release_urls()

    def build(self):
        logger.debug("[BUILD] %s%s" % (self.name, " %s" % self.version if self.version else ""))

        # Check to Make sure fetch has been ran
        if not hasattr(self, "releases") or not hasattr(self, "release_data") or not hasattr(self, "release_url_data"):
            raise Exception("fetch must be called prior to running build")  # @@@ Make a Custom Exception

        # Construct our representation of the releases
        self.data = {}
        for release in self.releases:
            data = {}

            data["package"] = self.name
            data["version"] = release

            data["author"] = get_helper(self.release_data[release], "author")
            data["author_email"] = get_helper(self.release_data[release], "author_email")

            data["maintainer"] = get_helper(self.release_data[release], "maintainer")
            data["maintainer_email"] = get_helper(self.release_data[release], "maintainer_email")

            data["summary"] = get_helper(self.release_data[release], "summary")
            data["description"] = get_helper(self.release_data[release], "description")

            data["license"] = get_helper(self.release_data[release], "license")
            data["keywords"] = get_helper(self.release_data[release], "keywords")  # @@@ Switch This to a List
            data["platform"] = get_helper(self.release_data[release], "platform")
            data["download_uri"] = get_helper(self.release_data[release], "download_url")  # @@@ Should This Go Under URI?
            data["requires_python"] = get_helper(self.release_data[release], "required_python")

            data["stable_version"] = get_helper(self.release_data[release], "stable_version")  # @@@ What Is This?

            data["classifiers"] = get_helper(self.release_data[release], "classifiers", [])

            # Construct the URIs
            data["uris"] = {}

            if get_helper(self.release_data[release], "home_page"):
                data["uris"]["Home Page"] = get_helper(self.release_data[release], "home_page")

            if get_helper(self.release_data[release], "bugtrack_url"):
                data["uris"]["Bug Tracker"] = get_helper(self.release_data[release], "bugtrack_url")

            for label, url in [x.split(",", 1) for x in get_helper(self.release_data[release], "project_url", [])]:
                data["uris"][label] = url

            # Construct Requires
            data["requires"] = []

            for kind in ["requires", "requires_dist", "requires_external"]:
                for require in get_helper(self.release_data[release], kind, []):
                    req = {"kind": kind if kind is not "requires_external" else "external"}
                    req.update(split_meta(require))
                    data["requires"].append(req)

            # Construct Provides
            data["provides"] = []

            for kind in ["provides", "provides_dist"]:
                for provides in get_helper(self.release_data[release], kind, []):
                    req = {"kind": kind}
                    req.update(split_meta(provides))
                    data["provides"].append(req)

            # Construct Obsoletes
            data["obsoletes"] = []

            for kind in ["obsoletes", "obsoletes_dist"]:
                for provides in get_helper(self.release_data[release], kind, []):
                    req = {"kind": kind}
                    req.update(split_meta(provides))
                    data["obsoletes"].append(req)

            # Construct Files
            data["files"] = []

            for url_data in self.release_url_data[release]:
                data["files"].append({
                    "comment": get_helper(url_data, "comment_text"),
                    "downloads": get_helper(url_data, "downloads", 0),
                    "file": get_helper(url_data, "url"),
                    "filename": get_helper(url_data, "filename"),
                    "python_version": get_helper(url_data, "python_version"),
                    "type": get_helper(url_data, "packagetype"),
                    "digests": {
                        "md5": url_data["md5_digest"].lower(),
                    }
                })
                if url_data.get("upload_time"):
                    data["files"][-1]["created"] = url_data["upload_time"].replace(tzinfo=utc)

            for file_data in data["files"]:
                if file_data.get("created"):
                    if data.get("created"):
                        if file_data["created"] < data["created"]:
                            data["created"] = file_data["created"]
                    else:
                        data["created"] = file_data["created"]

            self.data[release] = data

            logger.debug("[RELEASE BUILD DATA] %s %s %s" % (self.name, release, data))

    def store(self):
        try:
            package = Package.objects.get(normalized_name=re.sub('[^A-Za-z0-9.]+', '-', self.name).lower())
            if package.name != self.name:
                package.name = self.name
                package.save()
        except Package.DoesNotExist:
            package = Package.objects.create(name=self.name)

        for data in self.data.values():
            try:
                release = Release.objects.get(package=package, version=data["version"])
            except Release.DoesNotExist:
                release = Release(package=package, version=data["version"])
                release.full_clean()
                release.save()

            # This is an extra database call but it should prevent ShareLocks
            Release.objects.filter(pk=release.pk).select_for_update()

            if release.hidden:
                release.hidden = False

            for key, value in data.iteritems():
                if key in ["package", "version"]:
                    # Short circuit package and version
                    continue

                if key == "uris":
                    ReleaseURI.objects.filter(release=release).delete()
                    for label, uri in value.iteritems():
                        try:
                            ReleaseURI.objects.get(release=release, label=label, uri=uri)
                        except ReleaseURI.DoesNotExist:
                            try:
                                release_uri = ReleaseURI(release=release, label=label, uri=uri)
                                release_uri.full_clean()
                                release_uri.save(force_insert=True)
                            except ValidationError:
                                logger.exception("%s, %s for %s-%s Invalid Data" % (label, uri, release.package.name, release.version))
                elif key == "classifiers":
                    release.classifiers.clear()
                    for classifier in value:
                        try:
                            trove = TroveClassifier.objects.get(trove=classifier)
                        except TroveClassifier.DoesNotExist:
                            trove = TroveClassifier(trove=classifier)
                            trove.full_clean()
                            trove.save(force_insert=True)
                        release.classifiers.add(trove)
                elif key in ["requires", "provides", "obsoletes"]:
                    model = {"requires": ReleaseRequire, "provides": ReleaseProvide, "obsoletes": ReleaseObsolete}.get(key)
                    model.objects.filter(release=release).delete()
                    for item in value:
                        try:
                            model.objects.get(release=release, **item)
                        except model.DoesNotExist:
                            m = model(release=release, **item)
                            m.full_clean()
                            m.save(force_insert=True)
                elif key == "files":
                    files = ReleaseFile.objects.filter(release=release)
                    filenames = dict([(x.filename, x) for x in files])

                    for f in value:
                        try:
                            rf = ReleaseFile.objects.get(
                                    release=release,
                                    type=f["type"],
                                    filename=f["filename"],
                                    python_version=f["python_version"],
                                )

                            for k, v in f.iteritems():
                                if k in ["digests", "file", "filename", "type", "python_version"]:
                                    continue
                                setattr(rf, k, v)

                            rf.hidden = False
                            rf.full_clean()
                            rf.save()

                        except ReleaseFile.DoesNotExist:
                            rf = ReleaseFile(
                                    release=release,
                                    type=f["type"],
                                    filename=f["filename"],
                                    python_version=f["python_version"],
                                    url=f["file"],
                                    **dict([(k, v) for k, v in f.iteritems() if k not in ["digests", "file", "filename", "type", "python_version"]])
                                )

                            rf.hidden = False
                            rf.full_clean()
                            rf.save()

                        if f["filename"] in filenames.keys():
                            del filenames[f["filename"]]

                    if filenames:
                        for rf in ReleaseFile.objects.filter(pk__in=[f.pk for f in filenames.values()]):
                            rf.hidden = True
                            rf.save()
                else:
                    setattr(release, key, value)

            while True:
                try:
                    release.full_clean()
                except ValidationError as e:
                    if "download_uri" in e.message_dict:
                        release.download_uri = ""
                        logger.exception("%s-%s Release Validation Error %s" % (release.package.name, release.version, str(e.message_dict)))
                    else:
                        raise
                else:
                    break
            release.save()

        # Mark unsynced as deleted when bulk processing
        if self.bulk:
            for release in Release.objects.filter(package=package).exclude(version__in=self.data.keys()):
                release.hidden = True
                release.save()

        self.stored = True

    def download(self):
        # Check to Make sure fetch has been ran
        if not hasattr(self, "releases") or not hasattr(self, "release_data") or not hasattr(self, "release_url_data"):
            raise Exception("fetch and build must be called prior to running download")  # @@@ Make a Custom Exception

        # Check to Make sure build has been ran
        if not hasattr(self, "data"):
            raise Exception("build must be called prior to running download")  # @@@ Make a Custom Exception

        if not self.stored:
            raise Exception("package must be stored prior to downloading")  # @@@ Make a Custom Exception

        pypi_pages = self.verify_and_sync_pages()

        for data in self.data.values():
            try:
                # if pypi_pages.get("has_sig"):
                #     simple_html = lxml.html.fromstring(pypi_pages["simple"])
                #     simple_html.make_links_absolute(urlparse.urljoin(SIMPLE_URL, data["package"]) + "/")

                #     verified_md5_hashes = {}

                #     for link in simple_html.iterlinks():
                #             m = _md5_re.search(link[2])
                #             if m:
                #                 url, md5_hash = m.groups()
                #                 verified_md5_hashes[url] = md5_hash

                package = Package.objects.get(name=data["package"])
                release = Release.objects.filter(package=package, version=data["version"]).select_for_update()

                for release_file in ReleaseFile.objects.filter(release=release, filename__in=[x["filename"] for x in data["files"]]).select_for_update():
                    file_data = [x for x in data["files"] if x["filename"] == release_file.filename][0]

                    datastore_key = "crate:pypi:download:%(url)s" % {"url": file_data["file"]}
                    stored_file_data = self.datastore.hgetall(datastore_key)

                    headers = None

                    if stored_file_data and self.skip_modified:
                        # Stored data exists for this file
                        if release_file.file:
                            try:
                                release_file.file.read()
                            except IOError:
                                pass
                            else:
                                # We already have a file
                                if stored_file_data["md5"].lower() == file_data["digests"]["md5"].lower():
                                    # The supposed MD5 from PyPI matches our local
                                    headers = {
                                        "If-Modified-Since": stored_file_data["modified"],
                                    }

                    resp = requests.get(file_data["file"], headers=headers, prefetch=True)

                    if resp.status_code == 304:
                        logger.info("[DOWNLOAD] skipping %(filename)s because it has not been modified" % {"filename": release_file.filename})
                        return
                    logger.info("[DOWNLOAD] downloading %(filename)s" % {"filename": release_file.filename})

                    resp.raise_for_status()

                    # Make sure the MD5 of the file we receive matched what we were told it is
                    if hashlib.md5(resp.content).hexdigest().lower() != file_data["digests"]["md5"].lower():
                        raise PackageHashMismatch("%s does not match %s for %s %s" % (
                                                            hashlib.md5(resp.content).hexdigest().lower(),
                                                            file_data["digests"]["md5"].lower(),
                                                            file_data["type"],
                                                            file_data["filename"],
                                                        ))

                    release_file.digest = "$".join(["sha256", hashlib.sha256(resp.content).hexdigest().lower()])

                    release_file.full_clean()
                    release_file.file.save(file_data["filename"], ContentFile(resp.content), save=False)
                    release_file.save()

                    Event.objects.create(
                        package=release_file.release.package.name,
                        version=release_file.release.version,
                        action=Event.ACTIONS.file_add,
                        data={
                            "filename": release_file.filename,
                            "digest": release_file.digest,
                            "uri": release_file.get_absolute_url(),
                        }
                    )

                    # Store data relating to this file (if modified etc)
                    stored_file_data = {
                        "md5": file_data["digests"]["md5"].lower(),
                        "modified": resp.headers.get("Last-Modified"),
                    }

                    if resp.headers.get("Last-Modified"):
                        self.datastore.hmset(datastore_key, {
                            "md5": file_data["digests"]["md5"].lower(),
                            "modified": resp.headers["Last-Modified"],
                        })
                        # Set a year expire on the key so that stale entries disappear
                        self.datastore.expire(datastore_key, 31556926)
                    else:
                        self.datastore.delete(datastore_key)
            except requests.HTTPError:
                logger.exception("[DOWNLOAD ERROR]")

    def get_releases(self):
        if self.version is None:
            releases = self.pypi.package_releases(self.name, True)
        else:
            releases = [self.version]

        logger.debug("[RELEASES] %s%s [%s]" % (self.name, " %s" % self.version if self.version else "", ", ".join(releases)))

        return releases

    def get_release_data(self):
        release_data = []
        for release in self.releases:
            data = self.pypi.release_data(self.name, release)
            logger.debug("[RELEASE DATA] %s %s" % (self.name, release))
            release_data.append([release, data])
        return dict(release_data)

    def get_release_urls(self):
        release_url_data = []
        for release in self.releases:
            data = self.pypi.release_urls(self.name, release)
            logger.info("[RELEASE URL] %s %s" % (self.name, release))
            logger.debug("[RELEASE URL DATA] %s %s %s" % (self.name, release, data))
            release_url_data.append([release, data])
        return dict(release_url_data)

    def verify_and_sync_pages(self):
        # Get the Server Key for PyPI
        try:
            # Download the "simple" page from PyPI for this package
            simple = requests.get(urlparse.urljoin(SIMPLE_URL, urllib.quote(self.name.encode("utf-8"))), prefetch=True)
            simple.raise_for_status()
        except requests.HTTPError:
            if simple.status_code == 404:
                return {"has_sig": False}
            raise
        except ValueError:
            logger.exception("Got a ValueError from downloading the Simple page")
            return {"has_sig": False}

        try:
            package = Package.objects.get(normalized_name=re.sub('[^A-Za-z0-9.]+', '-', self.name).lower())
        except Package.DoesNotExist:
            logger.exception("Error Trying To Verify %s (Querying Package)" % self.name)
            return

        simple_mirror, c = PyPIMirrorPage.objects.get_or_create(package=package, defaults={"content": simple.content})
        if not c and simple_mirror.content != simple.content:
            simple_mirror.content = simple.content
            simple_mirror.save()


        return {
            "simple": simple.content,
            "has_sig": False,
        }
