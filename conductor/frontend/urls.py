# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

from django.urls import path

from . import views


urlpatterns = [
    path('', views.index),
    path('project/<int:project_id>/', views.project, name="project-details"),
    path('project/<int:project_id>/startqa/<int:ci_id>', views.start_project_qa, name="projectstartqa"),
]
