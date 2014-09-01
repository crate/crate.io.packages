# -*- coding: utf-8 -*-
import os.path
import posixpath

import djcelery

djcelery.setup_loader()

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))

DEBUG = False
TEMPLATE_DEBUG = True

SERVE_MEDIA = DEBUG

INTERNAL_IPS = [
    "127.0.0.1",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": "crate",
        "USER": "crate",
        "HOST": "127.0.0.1",
        "PORT": "5432"
    }
}

HAYSTACK_CONNECTIONS = {
  "default": {
    "ENGINE": "haystack.backends.elasticsearch_backend.ElasticsearchSearchEngine",
    "URL": "http://127.0.0.1:9200/",
    "INDEX_NAME": "crate-dev",
  },
}

TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"

USE_I18N = True
USE_L10N = True
USE_TZ = True

LOCALE_PATHS = [
    os.path.join(PROJECT_ROOT, os.pardir, "locale"),
]

LANGUAGES = (
    ("en", "English"),

    ("de", "German"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("pt-br", "Portuguese (Brazil)"),
    ("ru", "Russian"),
)

MEDIA_ROOT = os.path.join(PROJECT_ROOT, "site_media", "media")
MEDIA_URL = "/site_media/media/"


STATIC_ROOT = os.path.join(PROJECT_ROOT, "site_media", "static")
STATIC_URL = "/site_media/static/"

ADMIN_MEDIA_PREFIX = posixpath.join(STATIC_URL, "admin/")

# STATICFILES_DIRS = [
#     os.path.join(PROJECT_ROOT, "static"),
# ]

STATICFILES_FINDERS = [
    "staticfiles.finders.FileSystemFinder",
    "staticfiles.finders.AppDirectoriesFinder",
    "staticfiles.finders.LegacyAppDirectoriesFinder",
]

TEMPLATE_LOADERS = [
    "jingo.Loader",
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]

JINGO_EXCLUDE_APPS = [
    "debug_toolbar",
    "admin",
    "admin_tools",
]

JINJA_CONFIG = {
    "extensions": [
        "jinja2.ext.i18n",
        "jinja2.ext.autoescape",
    ],
}

MIDDLEWARE_CLASSES = [
    "django_hosts.middleware.HostsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "account.middleware.LocaleMiddleware",
]

ROOT_URLCONF = "crateweb.root_urls"
ROOT_HOSTCONF = "crateweb.hosts"

DEFAULT_HOST = "default"

WSGI_APPLICATION = "crateweb.wsgi.application"

TEMPLATE_DIRS = [
    os.path.join(PROJECT_ROOT, "templates"),
    os.path.join(PROJECT_ROOT, "templates", "_dtl"),
]

TEMPLATE_CONTEXT_PROCESSORS = [
    "django.contrib.auth.context_processors.auth",
    "django.core.context_processors.debug",
    "django.core.context_processors.i18n",
    "django.core.context_processors.media",
    "django.core.context_processors.request",
    "django.contrib.messages.context_processors.messages",
    "staticfiles.context_processors.static",
    "pinax_utils.context_processors.settings",
    "account.context_processors.account",
    "social_auth.context_processors.social_auth_by_type_backends",
]

INSTALLED_APPS = [
    # Admin Dashboard
    "admin_tools",
    "admin_tools.theming",
    "admin_tools.menu",
    "admin_tools.dashboard",

    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.humanize",
    "django.contrib.markup",

    # Authentication / Accounts
    "account",
    "social_auth",

    # Static Files
    "staticfiles",

    # Backend Tasks
    "djcelery",

    # Search
    "haystack",
    "celery_haystack",
    "saved_searches",

    # Database
    "south",

    # API
    "tastypie",

    # Utility
    "django_hosts",
    "storages",
    #"djangosecure",

    # Templating
    "jingo",

    "jutils.jhumanize",
    "jutils.jmetron",
    "jutils.jintercom",

    # project
    "crate.web.theme",
    "crate.web.packages",
    "crate.web.search",
    "crate.web.history",
    "crate.web.lists",
    "crate.web.utils",
    "crate.pypi",

    "cmds",
]

FIXTURE_DIRS = [
    os.path.join(PROJECT_ROOT, "fixtures"),
]

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

ACCOUNT_OPEN_SIGNUP = True
ACCOUNT_EMAIL_UNIQUE = True
ACCOUNT_EMAIL_CONFIRMATION_REQUIRED = True
ACCOUNT_EMAIL_CONFIRMATION_EMAIL = True
ACCOUNT_CONTACT_EMAIL = "support@crate.io"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "crate.web.social_auth.backends.OpenIDBackend",
    "social_auth.backends.contrib.github.GithubBackend",
    "social_auth.backends.contrib.bitbucket.BitbucketBackend",
]

SOCIAL_AUTH_PIPELINE = [
    "social_auth.backends.pipeline.social.social_auth_user",
    "crate.web.social_auth.pipeline.associate.associate_by_email",
    "social_auth.backends.pipeline.user.get_username",
    "crate.web.social_auth.pipeline.user.create_user",
    "social_auth.backends.pipeline.social.associate_user",
    "social_auth.backends.pipeline.social.load_extra_data",
    "social_auth.backends.pipeline.user.update_user_details",
]

PASSWORD_HASHERS = (
    "django.contrib.auth.hashers.BCryptPasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.SHA1PasswordHasher",
    "django.contrib.auth.hashers.MD5PasswordHasher",
    "django.contrib.auth.hashers.CryptPasswordHasher",
)

GITHUB_EXTRA_DATA = [
    ("login", "display"),
]

SOCIAL_AUTH_ASSOCIATE_BY_MAIL = False

LOGIN_URL = "/account/login/"
LOGIN_REDIRECT_URL = "/"
LOGIN_ERROR_URL = "/"
LOGIN_REDIRECT_URLNAME = "search"
LOGOUT_REDIRECT_URLNAME = "search"

EMAIL_CONFIRMATION_DAYS = 2
EMAIL_DEBUG = DEBUG

DEBUG_TOOLBAR_CONFIG = {
    "INTERCEPT_REDIRECTS": False,
}

CELERY_SEND_TASK_ERROR_EMAILS = True
CELERY_DISABLE_RATE_LIMITS = True
CELERY_TASK_PUBLISH_RETRY = True

CELERYD_MAX_TASKS_PER_CHILD = 10000

CELERY_IGNORE_RESULT = True

CELERY_TASK_RESULT_EXPIRES = 7 * 24 * 60 * 60  # 7 Days

CELERYD_HIJACK_ROOT_LOGGER = False

CELERYBEAT_SCHEDULER = "djcelery.schedulers.DatabaseScheduler"

ADMIN_TOOLS_INDEX_DASHBOARD = "crate.web.dashboard.CrateIndexDashboard"
