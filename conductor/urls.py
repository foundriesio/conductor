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
from django.urls import path, include
import django.contrib.auth.views as auth

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('conductor.api.urls')),
    path('login/', auth.LoginView.as_view(template_name="account/login.html")),
    path('accounts/', include('allauth.urls')),
    path(r'', include('conductor.frontend.urls'))
]
