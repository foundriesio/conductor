# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

import io
import yaml
import zipfile

from django.contrib import admin
from django.http import HttpResponse
from django.utils.text import slugify
from . import models
from .tasks import create_build_run

class LAVABackendAdmin(admin.ModelAdmin):
    models = models.LAVABackend


class SQUADBackendAdmin(admin.ModelAdmin):
    models = models.SQUADBackend


class ProjectAdmin(admin.ModelAdmin):
    models = models.Project
    list_display = ("name", "create_ota_commit", "create_containers_commit","test_on_merge_only", "apply_tag_to_first_build_only", "test_static_delta","disabled",)
    list_filter = ("create_ota_commit", "create_containers_commit","test_on_merge_only", "apply_tag_to_first_build_only", "test_static_delta", "disabled", "qa_reports_project_name", "forked_from",)


@admin.action(description='Create LAVA templates')
def create_lava_templates(modeladmin, request, queryset):
    testjob_list = []
    for build in queryset:
        runs = build.run_set.all()
        if not runs.exists():
            # upgrade build. Runs belong to 'previous build'

            previous_builds = build.project.build_set.filter(build_id__lt=build.build_id, tag=build.tag).order_by('-build_id')
            previous_build = None
            if previous_builds:
                previous_build = previous_builds[0]
                runs = previous_build.run_set.all()
        for run in runs:
            testjob_list = testjob_list + create_build_run(build.pk, run.run_name, False)

    if not testjob_list:
        # return early when the list is empty
        return
    tmp = io.BytesIO()
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, False) as archive:
        for index, testjob in enumerate(testjob_list):
            testjob_yaml = yaml.load(testjob, Loader=yaml.SafeLoader)
            filename = slugify(testjob_yaml.get("job_name", index))
            devicetype = slugify(testjob_yaml.get("device_type", None))
            archive.writestr(f"{index}-{filename}-{devicetype}.yaml", testjob.encode())
    response = HttpResponse(tmp.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="lava.zip"'
    return response


class BuildAdmin(admin.ModelAdmin):
    models = models.Build
    actions = [create_lava_templates]


class BuildTagAdmin(admin.ModelAdmin):
    models = models.BuildTag


class RunAdmin(admin.ModelAdmin):
    models = models.Run


class LAVADeviceTypeAdmin(admin.ModelAdmin):
    models = models.LAVADeviceType
    list_filter = ('project',)


@admin.action(description="Remove from factory")
def remove_device_from_factory(modeladmin, request, queryset):
    for device in queryset:
        if device.auto_register_name is not None:
            factory_name = device.project.name
            device.remove_from_factory(factory=factory_name)


@admin.action(description="Remove from EL2GO")
def remove_device_from_el2go(modeladmin, request, queryset):
    for device in queryset:
        if device.el2go_name is not None:
            device.remove_from_el2go()


@admin.action(description="Add to EL2GO")
def add_device_to_el2go(modeladmin, request, queryset):
    for device in queryset:
        if device.el2go_name is not None:
            device.remove_from_el2go()


class LAVADeviceAdmin(admin.ModelAdmin):
    models = models.LAVADevice
    list_filter = ('project', 'device_type')
    actions = [remove_device_from_factory, remove_device_from_el2go, add_device_to_el2go]


class LAVAJobAdmin(admin.ModelAdmin):
    models = models.LAVAJob


admin.site.register(models.LAVABackend, LAVABackendAdmin)
admin.site.register(models.SQUADBackend, SQUADBackendAdmin)
admin.site.register(models.Project, ProjectAdmin)
admin.site.register(models.Build, BuildAdmin)
admin.site.register(models.BuildTag, BuildTagAdmin)
admin.site.register(models.Run, RunAdmin)
admin.site.register(models.LAVADeviceType, LAVADeviceTypeAdmin)
admin.site.register(models.LAVADevice, LAVADeviceAdmin)
admin.site.register(models.LAVAJob, LAVAJobAdmin)
