# Copyright 2021-2023 Foundries.io
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

import hashlib
import hmac
import json
import logging
from celery import chain, group
from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.http import (
    HttpResponse,
    HttpResponseNotAllowed,
    HttpResponseForbidden,
    HttpResponseBadRequest,
    HttpResponseNotFound,
    JsonResponse
)
from django.views.decorators.csrf import csrf_exempt

from conductor.api.models import APICallback
from conductor.core.models import Project, Build, LAVADevice, Run
from conductor.core.tasks import (
    create_build_run,
    merge_lmp_manifest,
    merge_project_lmp_manifest,
    update_build_commit_id,
    check_device_ota_completed,
    tag_build_runs,
    schedule_lmp_pr_tests,
    restart_failed_runs,
    schedule_static_delta
)
from conductor.core.utils import ISO8601_JSONEncoder


logger = logging.getLogger()


def process_lava_notification(request, job_id, job_status):
    pass


def __verify_header_auth(request, header_name="X-JobServ-Sig"):
    request_body_json = None
    if request.method == 'POST':

        # get headers
        header_token = request.headers.get(header_name, None)
        if not header_token:
            return HttpResponseForbidden()
        try:
            request_body_json = json.loads(request.body)
            build_url = request_body_json.get("url")
            if not build_url and not request_body_json.get("project"):
                return HttpResponseBadRequest()
            #"url": "https://api.foundries.io/projects/milosz-rpi3/lmp/builds/73/",
            project_name = None
            try:
                project_name = build_url.split("/")[4]
            except IndexError:
                return HttpResponseBadRequest()
            except AttributeError:
                project_name = request_body_json.get("project")
                if project_name is None:
                    return HttpResponseBadRequest()
            project = get_object_or_404(Project, name=project_name)
            sha256_digest = header_token.split(":", 1)[1].strip()
            data = json.dumps(request_body_json, cls=ISO8601_JSONEncoder)
            #data = json.dumps(request_body_json, cls=json.JSONEncoder)
            sig = hmac.new(project.secret.encode(), msg=request.body, digestmod="sha256")
            if not hmac.compare_digest(sig.hexdigest(), sha256_digest):
                logger.warning(f"Incorrect jobserv secret for project: {project.name}")
                # check if secret in the request matches one
                # stored in the project settings
                return HttpResponseForbidden()
        except json.decoder.JSONDecodeError:
            return HttpResponseBadRequest()
    else:
        return HttpResponseNotAllowed(["POST"])
    return request_body_json


@csrf_exempt
def process_device_webhook(request):
    """
    Expected request body:
    {
        "name": "device_auto_register_name",
        "project": "factory/project name"
    }
    """
    request_body_json = __verify_header_auth(request, header_name="X-DeviceOta-Sig")
    if isinstance(request_body_json, HttpResponse):
        return request_body_json
    APICallback.objects.create(
        endpoint="device",
        content=json.dumps(request_body_json)
    )
    project_name = request_body_json.get("project")
    device_name = request_body_json.get("name")
    logger.info(f"Checking device: {device_name} from {project_name}")
    project = get_object_or_404(Project, name=project_name)
    try:
        device = project.lavadevice_set.get(auto_register_name=device_name)
        check_device_ota_completed.delay(device_name, project_name)
    except LAVADevice.DoesNotExist:
        logger.warning(f"Device {device_name} not found in project {project_name}")
        return HttpResponseNotFound()
    return HttpResponse("OK")


@csrf_exempt
def process_jobserv_webhook(request):
    request_body_json = __verify_header_auth(request)
    if isinstance(request_body_json, HttpResponse):
        return request_body_json
    APICallback.objects.create(
        endpoint="jobserv",
        content=json.dumps(request_body_json)
    )
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
    build_status = request_body_json.get("status")
    project = get_object_or_404(Project, name=project_name)
    build = None
    if "containers" in trigger_name or \
            "platform" in trigger_name or \
            "generate-static-deltas" in trigger_name:
        # create new Build
        build_branch = None
        build_type = Build.BUILD_TYPE_REGULAR
        if not "generate-static-deltas" in trigger_name:
            build_branch = trigger_name.split("-")[1]
        else:
            build_type = Build.BUILD_TYPE_STATIC_DELTA
        build, _ = Build.objects.get_or_create(
            url=build_url,
            project=project,
            build_id=build_id,
            tag=build_branch,
            defaults={"build_status": build_status,
                      "build_type": build_type})
    if not build:
        # in case build is not created, exit gracefully
        return HttpResponse("OK")

    if build_status != "PASSED":
        restart_failed_runs.delay(build.pk, request_body_json)
        return HttpResponse("OK")

    if "generate-static-deltas" in trigger_name:
        build.reason = request_body_json.get("reason")
        build.save()
        schedule_static_delta.delay(build.pk)
        return HttpResponse("Created", status=201)

    if "containers" in trigger_name:
        # only create build and tag it
        # build won't have a commit ID in conductor DB
        tag_build_runs.delay(build.pk)
        return HttpResponse("Created", status=201)
    # only trigger testing round when build comes from proper branch
    if "platform" in trigger_name and project.default_branch in trigger_name:
        run_url = None
        build_run_list = []
        for run in request_body_json.get("runs"):
            run_url = run.get("url")
            run_name = run.get("name")
            build_run_list.append(create_build_run.si(build.pk, run_name))
        if run_url is not None:
            # only call update_build_commit_id once as
            # all runs should contain identical GIT_SHA
            workflow = (update_build_commit_id.si(build.pk, run_url)| tag_build_runs.si(build.pk) | group(build_run_list))
            workflow.delay()

        return HttpResponse("Created", status=201)
    return HttpResponse("OK")


@csrf_exempt
def process_lmp_build(request):
    request_body_json = __verify_header_auth(request)
    if isinstance(request_body_json, HttpResponse):
        return request_body_json
    else:
        APICallback.objects.create(
            endpoint="lmp",
            content=json.dumps(request_body_json)
        )
        # check if build is successful
        if not request_body_json.get("status") == "PASSED":
            logger.warning("status not set to PASSED")
            return HttpResponse("OK")
        # check if the build has trigger_name "build-release"
        if request_body_json.get("trigger_name") in ["build-release", "build-release-stable"]:
            merge_lmp_manifest.delay()
            return HttpResponse("Created", status=201)
        if request_body_json.get("trigger_name") in ["Code Review"]:
            schedule_lmp_pr_tests.delay(request_body_json)
            return HttpResponse("Created", status=201)
    return HttpResponse("Created", status=201)


@csrf_exempt
def generate_context(request, project_name, build_version, device_type_name):
    project = get_object_or_404(Project, name=project_name)
    build = get_object_or_404(Build, project=project, build_id=build_version)
    try:
        context = build.generate_context(device_type_name)
        return JsonResponse(context)
    except Run.DoesNotExist:
        return HttpResponseNotFound()


@csrf_exempt
def process_github_webhook(request):
    """Verify that the payload was sent from GitHub by validating SHA256.

    Raise and return 403 if not authorized.

    Projects must share a secret if they inherit the same partner manifest
    """
    request_body_json = json.loads(request.body)
    APICallback.objects.create(
        endpoint="github",
        content=json.dumps(request_body_json)
    )

    signature_header = request.headers.get("X-Hub-Signature-256", None)
    projects = Project.objects.filter(fio_lmp_manifest_url = f"https://github.com/{request_body_json['repository']['full_name']}")
    project = None
    if not projects:
        return HttpResponseForbidden()

    if not signature_header:
        return HttpResponseForbidden()
    for project in projects:
        hash_object = hmac.new(project.secret.encode('utf-8'), msg=request.body, digestmod=hashlib.sha256)
        expected_signature = "sha256=" + hash_object.hexdigest()
        if not hmac.compare_digest(expected_signature, signature_header):
            continue
        # launch merge event for the project lmp-manifest repository
        merge_project_lmp_manifest.delay(project.id)
    return HttpResponse("OK")
