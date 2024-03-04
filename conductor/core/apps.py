# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'conductor.core'

    def ready(self):
        import conductor.core.signals  # noqa
