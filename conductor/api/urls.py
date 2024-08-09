# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

from django.urls import path

from . import views


urlpatterns = [
    path('jobserv/', views.process_jobserv_webhook),
    path('device/', views.process_device_webhook),
    path('lmp/', views.process_lmp_build),
    path('partner/', views.process_partner_build),
    path('github/', views.process_github_webhook),
    path('lavajob/([0-9]+)/(?:Submitted|Running|Canceling|Complete|Incomplete|Canceled)', views.process_lava_notification),
    path('context/<slug:project_name>/<int:build_version>/<slug:device_type_name>/', views.generate_context),
    path('test/apps/<slug:factory_name>/<slug:device_name>/', views.process_test_apps_request),
    path('test/tags/<slug:factory_name>/<slug:device_name>/', views.process_test_tags_request)
]
