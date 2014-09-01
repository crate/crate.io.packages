import os
import urlparse

from ..base import *

LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "formatters": {
        "simple": {
            "format": "%(levelname)s %(message)s"
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple"
        },
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
        "sentry": {
            "level": "ERROR",
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console", "sentry"],
        "level": "INFO",
    },
    "loggers": {
        "django.request": {
            "handlers": ["mail_admins"],
            "level": "ERROR",
            "propagate": True,
        },
        "sentry.errors": {
            "level": "DEBUG",
            "handlers": ["console"],
            "propagate": False,
        },
    }
}

if "DATABASE_URL" in os.environ:
    urlparse.uses_netloc.append("postgres")
    url = urlparse.urlparse(os.environ["DATABASE_URL"])
    DATABASES = {
        "default": {
            "ENGINE": {
                "postgres": "django.db.backends.postgresql_psycopg2"
            }[url.scheme],
            "NAME": url.path[1:],
            "USER": url.username,
            "PASSWORD": url.password,
            "HOST": url.hostname,
            "PORT": url.port
        }
    }

if "REDIS_URL" in os.environ:
    urlparse.uses_netloc.append("redis")
    url = urlparse.urlparse(os.environ["REDIS_URL"])

    REDIS = {
        "default": {
            "HOST": url.hostname,
            "PORT": url.port,
            "PASSWORD": url.password,
        }
    }

    CACHES = {
       "default": {
            "BACKEND": "redis_cache.RedisCache",
            "LOCATION": "%(HOST)s:%(PORT)s" % REDIS["default"],
            "KEY_PREFIX": "cache",
            "OPTIONS": {
                "DB": 0,
                "PASSWORD": REDIS["default"]["PASSWORD"],
            }
        }
    }

    PYPI_DATASTORE = "default"

    LOCK_DATASTORE = "default"

    # Celery Broker
    BROKER_TRANSPORT = "redis"

    BROKER_HOST = REDIS["default"]["HOST"]
    BROKER_PORT = REDIS["default"]["PORT"]
    BROKER_PASSWORD = REDIS["default"]["PASSWORD"]
    BROKER_VHOST = "0"

    BROKER_POOL_LIMIT = 10

    # Celery Results
    CELERY_RESULT_BACKEND = "redis"

    CELERY_REDIS_HOST = REDIS["default"]["HOST"]
    CELERY_REDIS_PORT = REDIS["default"]["PORT"]
    CELERY_REDIS_PASSWORD = REDIS["default"]["PORT"]

SITE_ID = 3

SERVER_EMAIL = "server@crate.io"
DEFAULT_FROM_EMAIL = "support@crate.io"

STATIC_URL = "https://crate.io/packages/static/"

ADMIN_MEDIA_PREFIX = STATIC_URL + "admin/"

SIMPLE_API_URL = "https://crate.io/packages"

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True

SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"

SECRET_KEY = os.environ["SECRET_KEY"]
