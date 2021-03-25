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

from django.contrib import admin
from . import models

class ProjectAdmin(admin.ModelAdmin):
    models = models.Project


class BuildAdmin(admin.ModelAdmin):
    models = models.Build


class RunAdmin(admin.ModelAdmin):
    models = models.Run


class LAVADeviceTypeAdmin(admin.ModelAdmin):
    models = models.LAVADeviceType


class LAVADeviceAdmin(admin.ModelAdmin):
    models = models.LAVADevice


class LAVAJobAdmin(admin.ModelAdmin):
    models = models.LAVAJob


class PDUAgentAdmin(admin.ModelAdmin):
    models = models.PDUAgent

admin.site.register(models.Project, ProjectAdmin)
admin.site.register(models.Build, BuildAdmin)
admin.site.register(models.Run, RunAdmin)
admin.site.register(models.LAVADeviceType, LAVADeviceTypeAdmin)
admin.site.register(models.LAVADevice, LAVADeviceAdmin)
admin.site.register(models.LAVAJob, LAVAJobAdmin)
admin.site.register(models.PDUAgent, PDUAgentAdmin)
