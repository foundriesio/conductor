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


@admin.action(description='Create LAVA templates')
def create_lava_templates(modeladmin, request, queryset):
    testjob_list = []
    for build in queryset:
        for run in build.run_set.all():
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


class LAVADeviceAdmin(admin.ModelAdmin):
    models = models.LAVADevice
    list_filter = ('project', 'device_type')


class LAVAJobAdmin(admin.ModelAdmin):
    models = models.LAVAJob


class PDUAgentAdmin(admin.ModelAdmin):
    models = models.PDUAgent
    list_display = ['__str__', 'state']

admin.site.register(models.LAVABackend, LAVABackendAdmin)
admin.site.register(models.SQUADBackend, SQUADBackendAdmin)
admin.site.register(models.Project, ProjectAdmin)
admin.site.register(models.Build, BuildAdmin)
admin.site.register(models.BuildTag, BuildTagAdmin)
admin.site.register(models.Run, RunAdmin)
admin.site.register(models.LAVADeviceType, LAVADeviceTypeAdmin)
admin.site.register(models.LAVADevice, LAVADeviceAdmin)
admin.site.register(models.LAVAJob, LAVAJobAdmin)
admin.site.register(models.PDUAgent, PDUAgentAdmin)
