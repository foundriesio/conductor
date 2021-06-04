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

import json
from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseForbidden, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

from conductor.core.models import Project, Build
from conductor.core.tasks import create_build_run, merge_lmp_manifest, update_build_commit_id


def process_lava_notification(request, job_id, job_status):
    pass


def __verify_jobserv(request):
    request_body_json = None
    if request.method == 'POST':

        # get headers
        header_token = request.headers.get("X-JobServ-Sig", None)
        if not header_token:
            return HttpResponseForbidden()
        try:
            request_body_json = json.loads(request.body)
        except json.decoder.JSONDecodeError:
            return HttpResponseBadRequest()
        header_token_sha256 = header_token.split(":", 1)[1].strip()
        request_body_json.update({"header": header_token_sha256})
        # get request body
        if request_body_json.get("status") != "PASSED":
            # nothing to do with failed build
            return HttpResponse("OK")
    else:
        return HttpResponseNotAllowed(["POST"])
    return request_body_json


@csrf_exempt
def process_jobserv_webhook(request):
    request_body_json = __verify_jobserv(request)
    if isinstance(request_body_json, HttpResponse):
        return request_body_json
    build_id = request_body_json.get("build_id")
    if not build_id:
        return HttpResponseBadRequest()
    build_url = request_body_json.get("url")
    if not build_url:
        return HttpResponseBadRequest()
    #"url": "https://api.foundries.io/projects/milosz-rpi3/lmp/builds/73/",
    project_name = None
    try:
        project_name = build_url.split("/")[4]
    except IndexError:
        return HttpResponseBadRequest()

    trigger_name = request_body_json.get("trigger_name")
    if "platform" not in trigger_name:
        # do nothing for container builds
        return HttpResponse("OK")
    project = get_object_or_404(Project, name=project_name)
    if not project.secret == request_body_json.get("header"):
        # check if secret in the request matches one
        # stored in the project settings
        return HttpResponseForbidden()
    # create new Build
    build, _ = Build.objects.get_or_create(url=build_url, project=project, build_id=build_id)
    run_url = None
    for run in request_body_json.get("runs"):
        run_url = run.get("url")
        run_name = run.get("name")
        create_build_run.delay(build.pk, run_url, run_name)
    if run_url is not None:
        # only call update_build_commit_id once as
        # all runs should contain identical GIT_SHA
        update_build_commit_id.delay(build.pk, run_url)

    return HttpResponse("Created", status=201)


@csrf_exempt
def process_lmp_build(request):
    request_body_json = __verify_jobserv(request)
    if isinstance(request_body_json, HttpResponse):
        return request_body_json
    else:
        # assume this call means successful LmP build
        merge_lmp_manifest.delay()
    return HttpResponse("OK")
