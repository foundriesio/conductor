# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'conductor.settings')

application = get_wsgi_application()
