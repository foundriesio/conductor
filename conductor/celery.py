# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

import os

from celery import Celery
from django.conf import settings  # noqa


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'conductor.settings')

app = Celery('conductor')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)
