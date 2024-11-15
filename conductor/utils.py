# Copyright 2024 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

import yaml
from django.urls import reverse


def get_admin_url(obj):
    return reverse('admin:%s_%s_change' % (obj._meta.app_label, obj._meta.model_name),
                   args=[obj.id])

def yaml_validator(value):
    if value is None:
        return
    if len(value) == 0:
        return
    try:
        if not isinstance(yaml.safe_load(value), dict):
            raise ValidationError("Dictionary object expected")
    except yaml.YAMLError as e:
        raise ValidationError(e)

