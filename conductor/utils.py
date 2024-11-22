# Copyright 2024 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

import yaml
from django.urls import reverse
from django.template import engines, TemplateSyntaxError


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

def template_from_string(template_string, using=None):
    """
    Convert a string into a template object,
    using a given template engine or using the default backends
    from settings.TEMPLATES if no engine was specified.
    """
    # This function is based on django.template.loader.get_template,
    # but uses Engine.from_string instead of Engine.get_template.
    chain = []
    engine_list = engines.all() if using is None else [engines[using]]
    for engine in engine_list:
        try:
            return engine.from_string(template_string)
        except TemplateSyntaxError as e:
            chain.append(e)
    raise TemplateSyntaxError(template_string, chain=chain)


def prepare_context(run_name, run_url, build_url, build_id):
    context = {
        "run_url": run_url,
        "run_name": run_name,
        "device_type": run_name,
        "build_url": build_url,
        "build_id": build_id,

        "IMAGE_URL": f"{run_url}lmp-base-console-image-{run_name}.wic.gz",
        "BOOTLOADER_URL": f"{run_url}simx-boot-run_name",
        "BOOTLOADER_NOHDMI_URL": f"{run_url}simx-boot-{run_name}-nohdmi",
        "SPLIMG_URL": f"{run_url}SPL-{run_name}",
        "MFGTOOL_URL": f"{build_url}runs/build-mfgtool-{run_name}/mfgtool-files.tar.gz",
        "MFGTOOL_BUILD_URL": f"{build_url}runs/build-mfgtool-{run_name}/",
        "prompts": [f"fio@{run_name}", "Password:", f"root@{run_name}"],
    }
    if run_name == "raspberrypi4-64":
        context["BOOTLOADER_URL"] = f"{run_url}other/u-boot-{run_name}.bin"
    if run_name == "stm32mp1-disco":
        context["BOOTLOADER_URL"] = f"{run_url}other/boot.itb"
    return context

