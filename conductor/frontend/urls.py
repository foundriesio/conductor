# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

from django.urls import path

from . import views


urlpatterns = [
    path('', views.index),
    path('project/<int:project_id>/', views.project, name="project-details"),
    path('project/<int:project_id>/startqa/<int:ci_id>', views.start_project_qa, name="projectstartqa"),
    path('project/<int:project_id>/starttests/<int:ci_id>', views.start_project_tests, name="projectstarttests"),
    path('project/<int:project_id>/startjob/<int:testjob_id>/testplan/<int:testplan_id>', views.start_project_testjob, name="projectstarttestjob"),
    path('project/<int:project_id>/startjob/<int:testjob_id>/testplan/<int:testplan_id>/build/<int:build_id>', views.run_project_testjob, name="projectruntestjob"),
]
