# Copyright 2022 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'conductor.testplan'

    def ready(self):
        import conductor.core.signals  # noqa
