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

from django.urls import path

from . import views


urlpatterns = [
    path('jobserv/', views.process_jobserv_webhook),
    path('device/', views.process_device_webhook),
    path('lmp/', views.process_lmp_build),
    path('github/', views.process_github_webhook),
    path('lavajob/([0-9]+)/(?:Submitted|Running|Canceling|Complete|Incomplete|Canceled)', views.process_lava_notification),
    path('context/<slug:project_name>/<int:build_version>/<slug:device_type_name>/', views.generate_context)
]
