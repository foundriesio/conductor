# Copyright 2024 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

from django.urls import reverse


def get_admin_url(obj):
    return reverse('admin:%s_%s_change' % (obj._meta.app_label, obj._meta.model_name),
                   args=[obj.id])
