# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

from django.contrib import admin
from django.urls import path, include
import django.contrib.auth.views as auth

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('conductor.api.urls')),
    path('login/', auth.LoginView.as_view(template_name="account/login.html")),
    path('accounts/', include('allauth.urls')),
    path(r'', include('conductor.frontend.urls'))
]
