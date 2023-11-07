# Copyright 2022 Foundries.io
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


class TimeoutAdmin(admin.ModelAdmin):
    models = models.Timeout


@admin.action(description="Render selected jobs")
def test_job_render(modeladmin, request, queryset):
    testjob_list = []
    tmp = io.BytesIO()
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, False) as archive:
        index = 0
        for testjob in queryset:
            testjob_yaml = testjob.get_job_definition(None)
            testjob_yaml_string = yaml.dump(testjob.get_job_definition(None), default_flow_style=False)
            filename = slugify(testjob_yaml.get("job_name", index))
            archive.writestr(f"{index}-{filename}.yaml", testjob_yaml_string.encode())
            index = index + 1
    response = HttpResponse(tmp.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="lava.zip"'
    return response


class TestJobAdmin(admin.ModelAdmin):
    models = models.TestJob
    save_as = True
    list_display = ('name', 'is_ota_job', 'is_downgrade_job', 'is_static_delta_job', 'is_el2go_job')
    list_filter = ('is_ota_job', 'is_downgrade_job', 'is_static_delta_job', 'is_el2go_job')
    actions = [test_job_render]


class TestJobContextAdmin(admin.ModelAdmin):
    models = models.TestJobContext


class TestJobTagAdmin(admin.ModelAdmin):
    models = models.TestJobTag


class TestJobMetadataAdmin(admin.ModelAdmin):
    models = models.TestJobMetadata


class DownloadImageAdmin(admin.ModelAdmin):
    models = models.DownloadImage
    save_as = True


class DeployPostprocessAdmin(admin.ModelAdmin):
    models = models.DeployPostprocess


class DeploymentAdmin(admin.ModelAdmin):
    models = models.Deployment
    list_display = ('name', 'namespace')
    save_as = True


class AutoLoginAdmin(admin.ModelAdmin):
    models = models.AutoLogin
    save_as = True


class BootAdmin(admin.ModelAdmin):
    list_display = ('name', 'namespace') 
    models = models.Boot
    save_as = True


class TestDefinitionAdmin(admin.ModelAdmin):
    models = models.TestDefinition
    list_display = ('name', 'testtype', 'device_type') 
    list_filter = ('testtype', 'device_type')
    save_as = True


class TestActionAdmin(admin.ModelAdmin):
    models = models.TestAction
    list_display = ('name', 'namespace') 
    save_as = True


class CommandActionAdmin(admin.ModelAdmin):
    models = models.CommandAction
    list_display = ('name', 'namespace') 
    save_as = True


class TestPlanAdmin(admin.ModelAdmin):
    models = models.TestPlan
    save_as = True


class InteractiveCommandAdmin(admin.ModelAdmin):
    models = models.InteractiveCommand


admin.site.register(models.Timeout, TimeoutAdmin)
admin.site.register(models.TestJob, TestJobAdmin)
admin.site.register(models.TestJobContext, TestJobContextAdmin)
admin.site.register(models.TestJobTag, TestJobTagAdmin)
admin.site.register(models.TestJobMetadata, TestJobMetadataAdmin)
admin.site.register(models.DownloadImage, DownloadImageAdmin)
admin.site.register(models.DeployPostprocess, DeployPostprocessAdmin)
admin.site.register(models.Deployment, DeploymentAdmin)
admin.site.register(models.AutoLogin, AutoLoginAdmin)
admin.site.register(models.Boot, BootAdmin)
admin.site.register(models.TestDefinition, TestDefinitionAdmin)
admin.site.register(models.TestAction, TestActionAdmin)
admin.site.register(models.CommandAction, CommandActionAdmin)
admin.site.register(models.TestPlan, TestPlanAdmin)
admin.site.register(models.InteractiveCommand, InteractiveCommandAdmin)
