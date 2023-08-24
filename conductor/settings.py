# Copyright 2021 Foundries.io
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
from celery.schedules import crontab
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'secret-key'

DEBUG = True
DEBUG_LAVA_SUBMIT = False
DEBUG_SQUAD_SUBMIT = False
DEBUG_FIO_SUBMIT = False
DEBUG_REPOSITORY_SCRIPTS = False

SITE_ID = 1  # required by allauth
ACCOUNT_EMAIL_VERIFICATION = 'none'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
ALLOWED_HOSTS = []
CSRF_TRUSTED_ORIGINS = ['https://conductor.infra.foundries.io']
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'polymorphic',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_celery_results',

    'sortedm2m',
    'conductor.core',
    'conductor.api',
    'conductor.pduserver',
    'conductor.frontend',
    'conductor.listener',
    'conductor.testplan',

    # google authentication
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.github',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
#    'allauth.account.auth_backends.AuthenticationBackend',
]


ROOT_URLCONF = 'conductor.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'conductor.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

CELERY_BROKER_URL = os.getenv('CONDUCTOR_CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = 'django-cache'
CELERY_TASK_ALWAYS_EAGER = CELERY_BROKER_URL is None
CELERY_TASK_STORE_EAGER_RESULTS = CELERY_TASK_ALWAYS_EAGER
CELERY_BROKER_CONNECTION_MAX_RETRIES = os.getenv('CONDUCTOR_CELERY_BROKER_CONNECTION_MAX_RETRIES', 5)
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'max_retries': CELERY_BROKER_CONNECTION_MAX_RETRIES,
    'queue_name_prefix': os.getenv('CONDUCTOR_CELERY_QUEUE_NAME_PREFIX', ''),
    'polling_interval': os.getenv('CONDUCTOR_CELERY_POLL_INTERVAL', 1),
}
CELERY_ACCEPT_CONTENT = ['json', 'yaml']
CELERY_TASK_SERIALIZER = 'json'
CELERY_BEAT_SCHEDULE_FILENAME = os.path.join(DATA_DIR, 'celerybeat-schedule')
CELERY_BEAT_SCHEDULE = {
    'check_ota_complete': {
        'task': 'conductor.core.tasks.check_ota_completed',
        'schedule': crontab(minute='*/10'),
    },
}

CELERY_TASK_DEFAULT_QUEUE = 'celery'
#CELERY_RESULT_BACKEND = 'django-db'
SILENCED_SYSTEM_CHECKS = ['urls.W002']

INTERNAL_ZMQ_SOCKET = "ipc:///tmp/conductor.msgs"
INTERNAL_ZMQ_TIMEOUT = 5

FIO_DOMAIN = "foundries.io"
FIO_API_TOKEN = os.getenv("FIO_API_TOKEN")
FIO_REPOSITORY_SCRIPT_PATH_PREFIX = f"{BASE_DIR}/conductor/scripts/"
FIO_REPOSITORY_TOKEN = os.getenv("FIO_REPOSITORY_TOKEN")
FIO_REPOSITORY_BASE = "https://source.%s/factories/"
FIO_REPOSITORY_HOME = "%s/repositories/" % BASE_DIR
FIO_REPOSITORY_CONTAINERS_HOME = "%s/containers/" % BASE_DIR
FIO_REPOSITORY_META_HOME = "%s/meta-sub/" % BASE_DIR
FIO_REPOSITORY_REMOTE_NAME = "origin"
FIO_BASE_MANIFEST = "https://github.com/foundriesio/lmp-manifest"
FIO_BASE_REMOTE_NAME = "lmp"
FIO_UPGRADE_ROLLBACK_MESSAGE = "upgrade/rollback testing"
FIO_UPGRADE_CONTAINER_MESSAGE = "Force container rebuild"
FIO_STATIC_DELTA_MESSAGE = "Building static deltas for Target"
FIO_LAVA_HEADER = "OSF-TOKEN"

GH_LMP_PATCH_SOURCE = "fio-github"

SKIP_QA_MESSAGES = ["[skip qa]", "[skip-qa]", "skip-qa"]
MAX_BUILD_RESTARTS = 3

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,
        },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
    }
}

try:
    from conductor.local_settings import *
except ImportError:
    pass
try:
    exec(open(os.getenv('CONDUCTOR_EXTRA_SETTINGS', '/dev/null')).read())
except FileNotFoundError:
    pass
