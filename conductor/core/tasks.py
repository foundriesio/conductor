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

import base64
import canonicaljson
import gitdb
import hashlib
import json
import os
import re
import requests
import subprocess
import yaml

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
)
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend

from conductor.celery import app as celery
from celery.utils.log import get_task_logger
from conductor.core.models import Run, Build, BuildTag, LAVADeviceType, LAVADevice, LAVAJob, Project
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.template.loader import get_template
from django.template import engines, TemplateSyntaxError
from django.utils import timezone
from git import Repo
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from urllib.parse import urljoin


logger = get_task_logger(__name__)
DEFAULT_TIMEOUT = 30

translate_result = {
    "pass": "PASSED",
    "fail": "FAILED",
    "skip": "SKIPPED",
    "unknown": "SKIPPED"
}

def requests_retry_session(
    retries=3,
    backoff_factor=1.0,
    status_forcelist=(500, ),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def _get_os_tree_hash(url, project):
    logger.debug("Retrieving ostree hash with base url: %s" % url)
    # ToDo: add headers for authentication
    token = project.fio_api_token
    if token is None:
        token = getattr(settings, "FIO_API_TOKEN", None)
    authentication = {
        "OSF-TOKEN": token,
    }
    session = requests.Session()
    session.headers.update(authentication)
    os_tree_hash_request = requests_retry_session(session=session).get(urljoin(url, "other/ostree.sha.txt"))
    if os_tree_hash_request.status_code == 200:
        return os_tree_hash_request.text.strip()
    return None


def _get_factory_targets(factory: str, token: str) -> dict:
    if token is None:
        token = getattr(settings, "FIO_API_TOKEN", None)
    authentication = {
        "OSF-TOKEN": token,
    }
    r = requests.get(
        f"https://api.foundries.io/ota/repo/{factory}/api/v1/user_repo/targets.json",
        headers=authentication,
    )
    try:
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.error(e)
        return None
    return r.json()


def _put_factory_targets(factory: str, checksum: str, targets: dict, token: str):
    if token is None:
        token = getattr(settings, "FIO_API_TOKEN", None)
    headers = {"OSF-TOKEN": token, "x-ats-role-checksum": checksum}
    logger.debug("PUTting new targets.json to the backend")
    r = requests.put(
        f"https://api.foundries.io/ota/repo/{factory}/api/v1/user_repo/targets",
        headers=headers,
        json=targets,
    )
    try:
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.error(e)
        logger.error(r.text)


def _change_tag(build, new_tag, add=True):
    logger.debug(f"Changing tag {new_tag} on the build {build} in factory {build.project}")

    if not build.project.privkey:
        logger.warning(f"No private key for project {build.project}")
        return None
    if not build.project.keyid:
        logger.warning(f"No ID for private key for project {build.project}")
        return None
    privbytes = build.project.privkey.encode()
    key = load_pem_private_key(privbytes, None, backend=default_backend())

    # add the tag to the target(s):
    meta = _get_factory_targets(build.project.name, build.project.fio_api_token)
    if not meta:
        logger.error("Empty targets JSON received")
        return
    m = hashlib.sha256()
    m.update(canonicaljson.encode_canonical_json(meta))
    checksum = m.hexdigest()

    for target in meta["signed"]["targets"].values():
        ver_str = target["custom"]["version"]
        ver = int(ver_str)
        if ver == build.build_id:
            if add:
                # add tag to target
                logger.debug(f"Adding tag {new_tag} to targets.json")
                target["custom"]["tags"].append(new_tag)
            else:
                # remove tag from target
                logger.debug(f"Removin tag {new_tag} from targets.json")
                if new_tag in target["custom"]["tags"]:
                    target["custom"]["tags"].remove(new_tag)

    meta["signed"]["version"] += 1
    meta["signatures"][0]["keyid"] = build.project.keyid

    # now sign data
    canonical = canonicaljson.encode_canonical_json(meta["signed"])
    sig = key.sign(
        canonical,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
        hashes.SHA256(),
    )
    assert len(meta["signatures"]) == 1
    meta["signatures"][0]["sig"] = base64.b64encode(sig).decode()
    if not settings.DEBUG_FIO_SUBMIT:
        _put_factory_targets(build.project.name, checksum, meta, build.project.fio_api_token)


def _add_tag(build, tag):
    logger.debug(f"Adding tag {tag} to the build {build} in factory {build.project}")
    _change_tag(build, tag.name, add=True)
    build.buildtag_set.add(tag)


def _remove_tag(build, tag):
    logger.debug(f"Removing tag {tag} from the build {build} in factory {build.project}")
    _change_tag(build, tag.name, add=False)
    oldtags = build.buildtag_set.filter(name=tag.name)
    if oldtags:
        for oldtag in oldtags:
            build.buildtag_set.remove(oldtag)


@celery.task(bind=True)
def tag_build_runs(self, build_id):
    logger.debug("Received tagging task for build: %s" % build_id)
    build = None
    try:
        build = Build.objects.get(pk=build_id)
    except Build.DoesNotExist:
        return None

    if not build.project.apply_testing_tag_on_callback:
        logger.info(f"Not setting tag on build {build}. Disabled in project settings")
        return None

    if not build.project.testing_tag:
        logger.debug("Nothing to do as project doesn't have testing tag")
        return None

    testing_buildtag, _ = BuildTag.objects.get_or_create(name=build.project.testing_tag)

    previous_builds = build.project.build_set.filter(build_id__lt=build.build_id, tag=build.tag).order_by('-build_id')
    previous_build = None
    old_tagged_builds = []
    if previous_builds:
        previous_build = previous_builds[0]
        old_tagged_builds = build.project.build_set.filter(buildtag=testing_buildtag, build_id__lt=previous_build.build_id)
        # there should only be 2 tagged builds: current and previous

    # remove tags from old builds
    for old_tagged_build in old_tagged_builds:
        _remove_tag(old_tagged_build, testing_buildtag)

    # tag current build
    _add_tag(build, testing_buildtag)
    return None


def _template_from_string(template_string, using=None):
    """
    Convert a string into a template object,
    using a given template engine or using the default backends
    from settings.TEMPLATES if no engine was specified.
    """
    # This function is based on django.template.loader.get_template,
    # but uses Engine.from_string instead of Engine.get_template.
    chain = []
    engine_list = engines.all() if using is None else [engines[using]]
    for engine in engine_list:
        try:
            return engine.from_string(template_string)
        except TemplateSyntaxError as e:
            chain.append(e)
    raise TemplateSyntaxError(template_string, chain=chain)


@celery.task(bind=True)
def create_build_run(self, build_id, run_name, submit_jobs=True):
    logger.debug("Received task for build: %s" % build_id)
    build = None
    try:
        build = Build.objects.get(pk=build_id)
    except Build.DoesNotExist:
        return None

    if not build.build_reason:
        update_build_reason.delay(build.id)
        # retry the same task in 1 minute
        raise self.retry(countdown=60)

    if not build.is_merge_commit and build.schedule_tests and build.project.test_on_merge_only:
        # don't schedule tests
        return None
    previous_builds = build.project.build_set.filter(build_id__lt=build.build_id, tag=build.tag).order_by('-build_id')
    previous_build = None
    if previous_builds:
        previous_build = previous_builds[0]
    device_type = None
    try:
        device_type = LAVADeviceType.objects.get(name=run_name, project=build.project)
    except LAVADeviceType.DoesNotExist:
        logger.debug(f"Device type {run_name} not found for {build.project}")
        return None

    templates = []
    # if there is a TestPlan object defined for the Project
    # use it to generate templates. Otherwise use the static rules
    # below
    if build.project.testplans.all():
        for plan in build.project.testplans.filter(lava_device_type=run_name):
            if build.build_reason and build.schedule_tests:
                for plan_testjob in plan.testjobs.filter(is_ota_job=False):
                    job_type = LAVAJob.JOB_LAVA
                    if plan_testjob.is_el2go_job:
                        job_type = LAVAJob.JOB_EL2GO
                    templates.append({
                        "name": plan_testjob.name,
                        "job_type": job_type,
                        "build": build,
                        "template": _template_from_string(yaml.dump(plan_testjob.get_job_definition(plan), default_flow_style=False))
                    })
            if build.build_reason and not build.schedule_tests:
                for plan_testjob in plan.testjobs.filter(is_ota_job=True):
                    job_type = LAVAJob.JOB_LAVA
                    if plan_testjob.is_el2go_job:
                        job_type = LAVAJob.JOB_EL2GO
                    templates.append({
                        "name": plan_testjob.name,
                        "job_type": job_type,
                        "build": previous_build,
                        "template": _template_from_string(yaml.dump(plan_testjob.get_job_definition(plan), default_flow_style=False))
                    })
    else:
        logger.info("Default test plan disabled")

    logger.debug(f"run_name: {run_name}")
    logger.debug(f"{templates}")
    lava_job_definitions = []
    for template in templates:
        lcl_build = template.get("build")
        if not lcl_build:
            continue
        run_url = f"{lcl_build.url}runs/{run_name}/"
        ostree_hash=_get_os_tree_hash(run_url, build.project)
        if not ostree_hash:
            logger.error("OSTree hash missing")
            continue

        run, _ = Run.objects.get_or_create(
            build=lcl_build,
            device_type=device_type,
            ostree_hash=ostree_hash,
            run_name=run_name
        )

        context = {
            "device_type": run_name,
            "build_url": lcl_build.url,
            "build_id": lcl_build.build_id,
            "build_commit": lcl_build.commit_id,
            "build_reason": lcl_build.build_reason,

            "IMAGE_URL": "%slmp-factory-image-%s.wic.gz" % (run_url, run_name),
            "BOOTLOADER_URL": "%simx-boot-%s" % (run_url, run_name),
            "BOOTLOADER_NOHDMI_URL": "%simx-boot-%s-nohdmi" % (run_url, run_name),
            "SPLIMG_URL": "%sSPL-%s" % (run_url, run_name),
            "MFGTOOL_URL": f"{lcl_build.url}runs/{run_name}-mfgtools/mfgtool-files.tar.gz",
            "prompts": ["fio@%s" % run_name, "Password:", "root@%s" % run_name],
            "net_interface": device_type.net_interface,
            "os_tree_hash": run.ostree_hash,
            "target": lcl_build.build_id,
            "ota_target": build.build_id,
        }
        if run_name == "raspberrypi4-64":
            context["BOOTLOADER_URL"] = "%sother/u-boot-%s.bin" % (run_url, run_name)
        if run_name == "stm32mp1-disco":
            context["BOOTLOADER_URL"] = "%sother/boot.itb" % (run_url)
        dt_settings = device_type.get_settings()
        for key, value in dt_settings.items():
            try:
                context.update({key: value.format(run_url=run_url, run_name=run_name)})
            except KeyError:
                # ignore KeyError in case of misformatted string
                pass
            except AttributeError:
                # ignore values that are not strings
                pass

        lava_job_definition = None
        if not template.get("template", None):
            lava_job_definition = get_template(template["name"]).render(context)
        else:
            lava_job_definition = template["template"].render(context)
        if not lava_job_definition:
            # possibly raise exception
            return
        lava_job_definitions.append(lava_job_definition)
        if not submit_jobs:
            continue
        job_ids = build.project.submit_lava_job(lava_job_definition)
        job_type=template.get("job_type")
        logger.debug(f"LAVA job IDs: {job_ids}")
        for job in job_ids:
            LAVAJob.objects.create(
                job_id=job,
                definition=lava_job_definition,
                project=build.project,
                job_type=job_type,
            )
            if job_type in [LAVAJob.JOB_LAVA, LAVAJob.JOB_EL2GO]:
                # returns HTTPResponse object or None
                watch_response = build.project.watch_qa_reports_job(lcl_build, run_name, job)
                if watch_response and watch_response.status_code == 201:
                    # update the testjob object in SQUAD
                    squad_job_id = watch_response.text
                    job_definition_yaml = yaml.safe_load(lava_job_definition)
                    job_name = job_definition_yaml.get('job_name')
                    build.project.squad_backend.update_testjob(squad_job_id, job_name, lava_job_definition)
    return lava_job_definitions


def _update_build_reason(build):
    if build.build_reason:
        return None
    repository_path = os.path.join(settings.FIO_REPOSITORY_HOME, build.project.name)
    repository = Repo(repository_path)
    old_commit = repository.commit("HEAD")
    try:
        remote = repository.remote(name=settings.FIO_REPOSITORY_REMOTE_NAME)
        remote.fetch()
        repository.git.reset("--hard", f"{settings.FIO_REPOSITORY_REMOTE_NAME}/{build.project.default_branch}")
        if build.commit_id:
            try:
                commit = repository.commit(rev=build.commit_id)
                logger.debug(f"Commit: {build.commit_id}")
                logger.debug(f"Commit message: {commit.message}")
                build.build_reason = commit.message[:127]
                if len(commit.parents) > 1:
                    build.is_merge_commit = True
                    # this is merge commit
                    for parent in commit.parents:
                        if parent.hexsha == old_commit.hexsha:
                            # this is previous HEAD
                            continue
                        build.lmp_commit = parent.hexsha
                else:
                    build.lmp_commit = commit.hexsha
            except ValueError:
                # commit was not found in the repository
                # this usually means build was triggered from meta-sub
                build.build_reason = "Trigerred from meta-sub"
            if settings.FIO_UPGRADE_ROLLBACK_MESSAGE in build.build_reason:
                build.schedule_tests = False

            build.save()
    except gitdb.exc.BadName:
        logger.warning(f"Commit {build.commit_id} not found in {build.project.name}")
        logger.info("fetching remote objects")


@celery.task
def update_build_commit_id(build_id, run_url):
    build = None
    try:
        build = Build.objects.get(pk=build_id)
    except Build.DoesNotExist:
        return None
    token = build.project.fio_api_token
    if token is None:
        token = getattr(settings, "FIO_API_TOKEN", None)
    authentication = {
        "OSF-TOKEN": token,
    }

    session = requests.Session()
    session.headers.update(authentication)
    run_json_request = requests_retry_session(session=session).get(urljoin(run_url, ".rundef.json"))
    if run_json_request.status_code == 200:
        with transaction.atomic():
            run_json = run_json_request.json()
            commit_id = run_json['env']['GIT_SHA']
            build.commit_id = commit_id
            build.save()
            _update_build_reason(build)
            build.refresh_from_db()
            if settings.FIO_UPGRADE_ROLLBACK_MESSAGE not in build.build_reason:
                create_upgrade_commit.delay(build_id)


@celery.task
def update_build_reason(build_id):
    build = None
    try:
        build = Build.objects.get(pk=build_id)
    except Build.DoesNotExist:
        return None

    _update_build_reason(build)


class ProjectMisconfiguredError(Exception):
    pass


def __project_repository_exists(project, base_path=settings.FIO_REPOSITORY_HOME):
    repository_path = os.path.join(base_path, project.name)
    if os.path.exists(repository_path):
        if os.path.isdir(repository_path):
            logger.info(f"Project repository for {project} exists in {base_path}")
            # do nothing, directory exists
            return True
        else:
            # raise exception, there should not be a file with this name
            logger.error(f"Project repository for {project} missing in {base_path}")
            raise ProjectMisconfiguredError()
    return False


@celery.task
def create_upgrade_commit(build_id):
    project = None
    build = None
    try:
        build = Build.objects.get(pk=build_id)
        project = build.project
    except Build.DoesNotExist:
        # do nothing if build is not found
        return
    if not project.create_ota_commit and not project.create_containers_commit:
        # don't create upgrade commit
        logger.info(f"Project {project} does not require additional OTA commit")
        return
    if not build.is_merge_commit and project.test_on_merge_only:
        # don't create upgrade commit
        logger.info(f"Project {project} only requires testing on merges. Skipping OTA commit")
        return
    cmd = []
    # produce containers commit if the setting is enabled
    if project.create_containers_commit:
        if not __project_repository_exists(project, settings.FIO_REPOSITORY_CONTAINERS_HOME):
            logger.error(f"Containers repository for {project} missing!")
            return
        if not project.compose_app_name or not project.compose_app_env_filename:
            logger.error(f"Container commit aborted. {project} not setup properly")
            return
        # change the content of the file and commit changes
        repository_path = os.path.join(settings.FIO_REPOSITORY_CONTAINERS_HOME, project.name)
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "upgrade_containers_commit.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-m", settings.FIO_UPGRADE_CONTAINER_MESSAGE,
               "-b", project.default_container_branch,
               "-f", f"{project.compose_app_name}/{project.compose_app_env_filename}"]
        # exit.
        logger.info(f"Processing project {project.name}")
        logger.info("Containers commit created. Skipping manifest content")
        # if containers_commit is enabled, there won't be manifest OTA
    else:
        # check if repository DIR already exists
        repository_path = os.path.join(settings.FIO_REPOSITORY_HOME, project.name)
        if not __project_repository_exists(project):
            logger.error(f"Repository for {project} missing!")
            return
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "upgrade_commit.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-m", settings.FIO_UPGRADE_ROLLBACK_MESSAGE,
               "-b", project.default_branch]
    if not settings.DEBUG_FIO_SUBMIT and cmd:
        logger.debug(f"{cmd}")
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            pass
    else:
        logger.debug("Debugging FIO submit")
        logger.debug(f"{cmd}")


@celery.task
def create_project_repository(project_id):
    project = None
    try:
        project = Project.objects.get(pk=project_id)
        fio_repository_token = project.fio_repository_token
        if not fio_repository_token:
            fio_repository_token = settings.FIO_REPOSITORY_TOKEN
    except Project.DoesNotExist:
        # do nothing if project is not found
        return
    # check if repository DIR already exists
    repository_path = os.path.join(settings.FIO_REPOSITORY_HOME, project.name)
    if not __project_repository_exists(project):
        # create repository DIR
        os.makedirs(repository_path)
    # call shell script to clone and configure repository
    cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "checkout_repository.sh"),
           "-d", repository_path,
           "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
           "-u", "%s/%s/lmp-manifest.git" % (settings.FIO_REPOSITORY_BASE, project.name),
           "-l", settings.FIO_BASE_REMOTE_NAME,
           "-w", settings.FIO_BASE_MANIFEST,
           "-t", fio_repository_token,
           "-b", project.default_branch]
    logger.debug("Calling repository creation script")
    logger.debug(" ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        pass

@celery.task
def create_project_containers_repository(project_id):
    project = None
    try:
        project = Project.objects.get(pk=project_id)
        fio_repository_token = project.fio_repository_token
        if not fio_repository_token:
            fio_repository_token = settings.FIO_REPOSITORY_TOKEN
    except Project.DoesNotExist:
        # do nothing if project is not found
        return
    # check if repository DIR already exists
    repository_path = os.path.join(settings.FIO_REPOSITORY_CONTAINERS_HOME, project.name)
    if not __project_repository_exists(project, settings.FIO_REPOSITORY_CONTAINERS_HOME):
        # create repository DIR
        os.makedirs(repository_path)
    # call shell script to clone and configure repository
    cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "checkout_repository.sh"),
           "-d", repository_path,
           "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
           "-u", "%s/%s/containers.git" % (settings.FIO_REPOSITORY_BASE, project.name),
           "-t", fio_repository_token,
           "-b", project.default_container_branch,
           "-c", "containers"]
    logger.debug("Calling repository creation script")
    logger.debug(" ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        pass


@celery.task
def merge_lmp_manifest():
    # merge LmP manifest into all project manifest repositories
    # don't touch LmP manifest itself. Project named 'lmp' is
    # a fake project that only keeps the API password.
    projects = Project.objects.all().exclude(name="lmp")
    for project in projects:
        repository_path = os.path.join(settings.FIO_REPOSITORY_HOME, project.name)
        if not __project_repository_exists(project):
            # ignore project with no repository
            continue
        # call shell script to merge manifests
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX,"merge_manifest.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-l", settings.FIO_BASE_REMOTE_NAME,
               "-b", project.default_branch]
        logger.info("Calling merge_manifest.sh script")
        logger.info(" ".join(cmd))
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            pass


#@celery.task
#def check_build_release():
#    # this task should run once or twice a day
#    # it fills in Build.is_release field based on the repository tags
#    pass


@celery.task
def device_pdu_action(device_id, power_on=True):
    lava_device = None
    try:
        lava_device = LAVADevice.objects.get(pk=device_id)
    except LAVADevice.DoesNotExist:
        return
    # get device dictionary
    device_dict_url = urljoin(lava_device.project.lava_backend.lava_url, f"devices/{lava_device.name}/dictionary?render=true")
    auth = {
        "Authorization": f"Token {lava_device.project.lava_backend.lava_api_token}"
    }
    device_request = requests.get(device_dict_url, headers=auth)
    device_dict = None
    if device_request.status_code == 200:
        device_dict = yaml.load(device_request.text, Loader=yaml.SafeLoader)
    # extract power on/off command(s)
    cmds = device_dict['commands']['power_on']
    logger.debug("Commands to be sent")
    logger.debug(cmds)
    if not power_on:
        cmds = device_dict['commands']['power_off']
    if not isinstance(cmds, list):
        cmds = [cmds]
    # use PDUAgent to run command(s) remotely
    if lava_device.pduagent:
        for cmd in cmds:
            lava_device.pduagent.message = cmd
            lava_device.pduagent.save()


def __get_testjob_results__(device, job_id):
    logger.debug(f"Retrieving result summary for job: {job_id}")
    current_target = device.get_current_target()
    target_name = current_target.get('target-name')
    lava_job_results = {}
    authentication = {
        "Authorization": "Token %s" % device.project.lava_backend.lava_api_token,
    }
    # get job definition
    definition_resp = requests.get(
        urljoin(device.project.lava_backend.lava_url, f"jobs/{job_id}/"),
        headers=authentication,
        timeout=DEFAULT_TIMEOUT
    )
    job_definition = None
    expected_test_list = []
    if definition_resp.status_code == 200:
        job_json = definition_resp.json()
        job_definition = yaml.load(job_json["definition"], Loader=yaml.SafeLoader)
        # todo: check if tests exist and they come with definitions
        # this is only correct for some test jobs
        for action in job_definition['actions']:
            if 'test' in action.keys() and 'definitions' in action['test'].keys():
                for expected_test in action['test']['definitions']:
                    expected_test_list.append(expected_test['name'])

    # compare job definition with results (any missing)?
    suites_resp = requests.get(
        urljoin(device.project.lava_backend.lava_url, f"jobs/{job_id}/suites/"),
        headers=authentication,
        timeout=DEFAULT_TIMEOUT
    )
    while suites_resp.status_code == 200:
        suites_content = suites_resp.json()
        for suite in suites_content['results']:
            if suite['name'] != 'lava':
                index, suite_name = suite['name'].split("_", 1)
                try:
                    expected_test_list.remove(suite_name)
                except ValueError:
                    logger.error(f"Suite {suite_name} not found in expected list")
                lava_job_results[suite_name] = {
                    "name": suite_name,
                    "status": "PASSED",
                    "target-name": target_name,
                    "results": []
                }
                tests_resp = requests.get(
                    urljoin(device.project.lava_backend.lava_url, f"jobs/{job_id}/suites/{suite['id']}/tests"),
                    headers=authentication,
                    timeout=DEFAULT_TIMEOUT
                )
                while tests_resp.status_code == 200:
                    tests_content = tests_resp.json()
                    for test_result in tests_content['results']:
                        #metadata = yaml.load(test_result['metadata'], Loader=yaml.SafeLoader)
                        lava_job_results[suite_name]['results'].append(
                            {
                                "name": test_result['name'],
                                "status": translate_result[test_result['result']],
                                "local_ts": 0
                            }
                        )

                    #lava_job_results[suite_name]['tests'] = lava_job_results[suite_name]['tests'] + tests_content['results']
                    if tests_content['next']:
                        tests_resp = requests.get(
                            tests_content['next'],
                            headers=authentication,
                            timeout=DEFAULT_TIMEOUT
                        )
                    else:
                        break
        if suites_content['next']:
            suites_resp = requests.get(
                suites_content['next'],
                headers=authentication,
                timeout=DEFAULT_TIMEOUT
            )
        else:
            break

    return lava_job_results


#def test_res(device, job_id):
#    return __get_testjob_results__(device, job_id)

@celery.task
def retrieve_lava_results(device_id, job_id):
    lava_db_device = None
    try:
        lava_db_device = LAVADevice.objects.get(pk=device_id)
    except LAVADevice.DoesNotExist:
        logger.debug(f"Device with ID {device_id} not found")
        return
    lava_results = __get_testjob_results__(lava_db_device, job_id)
    for suite_name, result in lava_results.items():
        __report_test_result(lava_db_device, result)


@celery.task
def process_testjob_notification(event_data):
    job_id = event_data.get("job")
    try:
        lava_job = LAVAJob.objects.get(job_id=job_id)
        device_name = event_data.get("device")
        lava_db_device = None
        logger.debug(f"Processing job: {job_id}")
        logger.debug(f"LAVA device name: {device_name}")
        if device_name:
            lava_db_device = LAVADevice.objects.get(name=device_name, project=lava_job.project)
            lava_job.device = lava_db_device
            lava_job.save()
            logger.debug(f"LAVA device is: {lava_db_device.id}")
        if lava_job.job_type == LAVAJob.JOB_OTA and \
                event_data.get("state") == "Running" and \
                lava_db_device:
            lava_db_device.request_maintenance()
        if lava_job.job_type == LAVAJob.JOB_OTA and \
                event_data.get("state") == "Finished" and \
                lava_db_device:
            if event_data.get("health") == "Complete":
                # remove device from factory at the latest possible moment
                lava_db_device.remove_from_factory(factory=lava_job.project.name)
                device_pdu_action(lava_db_device.id, power_on=True)
            else:
                # report OTA failure?
                lava_db_device.request_online()
                logger.error("OTA flashing job failed!")
        if lava_job.job_type == LAVAJob.JOB_LAVA and \
                event_data.get("state") == "Running" and \
                lava_db_device:
            # remove device from factory so it can autoregister
            # and update it's target ID
            lava_db_device.remove_from_factory(factory=lava_job.project.name)
        if lava_job.job_type == LAVAJob.JOB_LAVA and \
                event_data.get("state") == "Finished" and \
                lava_db_device:
            retrieve_lava_results(lava_db_device.id, job_id)
        if lava_job.job_type == LAVAJob.JOB_EL2GO and \
                event_data.get("state") == "Running" and \
                lava_db_device:
            # remove device from factory so it can autoregister
            # and update it's target ID
            lava_db_device.remove_from_factory(factory=lava_job.project.name)
            # add 2 EL2GO so the device can retrieve credentials
            lava_db_device.add_to_el2go()
        if lava_job.job_type == LAVAJob.JOB_EL2GO and \
                event_data.get("state") == "Finished" and \
                lava_db_device:
            retrieve_lava_results(lava_db_device.id, job_id)
            # remove EL2GO so the device can retrieve credentials
            # in the next job
            lava_db_device.remove_from_el2go()

    except LAVAJob.DoesNotExist:
        logger.debug(f"Job {job_id} not found")
        return
    except LAVADevice.DoesNotExist:
        logger.debug(f"Device from job {job_id} not found")
        return


@celery.task
def process_device_notification(event_data):
    pass


def __report_test_result(device, result):
    token = device.project.fio_api_token
    if token is None:
        # fallback to the global token
        # this will be phased out in the next version
        token = getattr(settings, "FIO_API_TOKEN", None)
    authentication = {
        "OSF-TOKEN": token,
    }

    url = f"https://api.foundries.io/ota/devices/{device.project.name}-{device.name}/tests/"
    test_dict = result.copy()
    test_dict.pop("status")
    new_test_request = requests.post(url, json=test_dict, headers=authentication)
    logger.info(f"Reporting test {result['name']} for {device.name}")
    if new_test_request.status_code == 201:
        test_details = new_test_request.json()
        result.update(test_details)
        details_url = f"{url}{test_details['test-id']}"
        update_details_request = requests.put(details_url, json=result, headers=authentication)
        if update_details_request.status_code == 200:
            logger.debug(f"Successfully reported details for {test_details['test-id']}")
        else:
            logger.warning(f"Failed to report details for {test_details['test-id']}")
    else:
        logger.warning(f"Failed to create test result for {device.project.name}-{device.name}")
        logger.warning(new_test_request.text)


@celery.task
def report_test_results(lava_device_id, target_name, ota_update_result=None, ota_update_from=None, result_dict=None):
    device = None
    try:
        device = LAVADevice.objects.get(pk=lava_device_id)
    except LAVADevice.DoesNotExist:
        logger.error(f"Device with ID: {lava_device_id} not found!")
        return
    if ota_update_result != None:
        test_name = f"ota_update_from_{ota_update_from}"
        test_result = "PASSED"
        if not ota_update_result:
            test_result = "FAILED"
        result = {
            "name": test_name,
            "status": test_result,
            "target-name": target_name
        }
        __report_test_result(device, result)
    elif result_dict != None:
        __report_test_result(device, result_dict)


def __check_ota_status(device):
    current_target = device.get_current_target()
    # determine whether current target is correct
    last_build = device.project.build_set.last()
    previous_builds = last_build.project.build_set.filter(build_id__lt=last_build.build_id).order_by('-build_id')
    previous_build = None
    if previous_builds:
        previous_build = previous_builds[0]
    try:
        last_run = last_build.run_set.get(run_name=device.device_type.name)
        target_name = current_target.get('target-name')
        if current_target.get('ostree-hash') == last_run.ostree_hash:
            # update successful
            logger.info(f"Device {device.name} successfully updated to {last_build.build_id}")
            report_test_results(device.id, target_name, ota_update_result=True, ota_update_from=previous_build.build_id)
        else:
            logger.info(f"Device {device.name} NOT updated to {last_build.build_id}")
            report_test_results(device.id, target_name, ota_update_result=False, ota_update_from=previous_build.build_id)

        # switch the device to LAVA control
        device.request_online()
        device.controlled_by = LAVADevice.CONTROL_LAVA
        device.save()
        device_pdu_action(device.id, power_on=False)
    except Run.DoesNotExist:
        logger.error(f"Run {device.device_type.name} for build {last_build.id} does not exist")


@celery.task
def check_device_ota_completed(device_name, project_name):
    try:
        device = LAVADevice.objects.get(auto_register_name=device_name, project__name=project_name)
        if device.controlled_by == LAVADevice.CONTROL_PDU:
            # only call __check_ota_status when the device is
            # in the upgrade mode
            __check_ota_status(device)
    except LAVADevice.DoesNotExist:
        logger.error(f"Device with name {device_name} not found in project {project_name}")


@celery.task
def check_ota_completed():
    # This is a periodic task which checks all devices which are in
    # OTA configuration. The default timeout for performing OTA and
    # running all tests is 30 minutes. If the device is not updated
    # after this timeout OTA is considered to be unsuccessful. The
    # device is moved back under LAVA control.
    deadline = timezone.now() - timedelta(minutes=30)
    devices = LAVADevice.objects.filter(
        controlled_by=LAVADevice.CONTROL_PDU,
        ota_started__lt=deadline
    )
    for device in devices:
        __check_ota_status(device)


@celery.task
def schedule_lmp_pr_tests(lmp_build_description):
    # This task will schedule boot test round on LmP PR
    # coming from meta-lmp in github

    # GitHub PR(338): pull_request, https://github.com/foundriesio/lmp-manifest/pull/338
    # extract PR URL
    reason = lmp_build_description.get("reason")
    owner = None
    repo = None
    gh_git_sha = None
    if reason:
        httpre = re.compile("(?P<url>https:\/\/[a-z0-9-\/\.]+)")
        results = httpre.search(reason)
        if results:
            gh_url = results.group("url")
            url_parts = gh_url.split("/")
            owner = url_parts[3]
            repo = url_parts[4]
            pr_num = url_parts[6]
            headers = {
                "Content-Type": "application/json",
            #    "Authorization": "token " + settings.META_LMP_GH_TOKEN,
            }
            pr_api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_num}"
            r = requests.get(pr_api_url, headers=headers)
            if r.status_code == 200:
                try:
                    data = r.json()
                    gh_git_sha = data["head"]["sha"]
                except Exception:
                    logger.error("Error finding SHA: %d - %s", r.status_code, r.text)

    # compose test jobs from lmp project
    # lmp project is special
    # build object won't be created (maybe it should?)

    # schedule tests through qa-reports with patch-source
    # this will allow to post a status on a PR

    project = None
    try:
        project = Project.objects.get(name="lmp")
    except Project.DoesNotExist:
        logger.error("Project lmp doesn't exist")
        return None

    # create qa-reports build with patch source
    project.squad_backend.create_build(
        "lmp",
        f"{project.name}",
        f"{gh_git_sha}",
        settings.GH_LMP_PATCH_SOURCE,
        f"{owner}/{repo}/{gh_git_sha}"
    )

    build_url = lmp_build_description.get("url")
    build_id = lmp_build_description.get("id")
    runs = lmp_build_description.get("runs")
    for run in runs:
        run_name = run.get("name")
        # all names in lmp "factory" start with "build-"
        #run_name_device_type = run_name.split("-", 1)[1]
        run_name = run_name.split("-", 1)[1]
        device_type = None
        try:
            device_type = LAVADeviceType.objects.get(name=run_name, project=project)
        except LAVADeviceType.DoesNotExist:
            logger.debug(f"Device type {run_name} not found for {project}")
            continue

        templates = []
        if project.testplans.all():
            for plan in project.testplans.filter(lava_device_type=run_name):
                for plan_testjob in plan.testjobs.filter(is_ota_job=False):
                    job_type = LAVAJob.JOB_LAVA
                    templates.append({
                        "name": plan_testjob.name,
                        "job_type": job_type,
                        "build": None,
                        "template": _template_from_string(yaml.dump(plan_testjob.get_job_definition(plan), default_flow_style=False))
                    })
        else:
            logger.info("Default test plan disabled")

        logger.debug(f"run_name: {run_name}")
        logger.debug(f"{templates}")
        lava_job_definitions = []
        for template in templates:
            run_url = run.get("url")

            context = {
                "device_type": run_name,
                "build_url": build_url,
                "build_id": build_id,
                "build_commit": gh_git_sha,
                "build_reason": reason,

                "IMAGE_URL": "%slmp-base-console-image-%s.wic.gz" % (run_url, run_name),
                "BOOTLOADER_URL": "%simx-boot-%s" % (run_url, run_name),
                "BOOTLOADER_NOHDMI_URL": "%simx-boot-%s-nohdmi" % (run_url, run_name),
                "SPLIMG_URL": "%sSPL-%s" % (run_url, run_name),
                "MFGTOOL_URL": f"{build_url}runs/build-mfgtool-{run_name}/mfgtool-files.tar.gz",
                "prompts": ["fio@%s" % run_name, "Password:", "root@%s" % run_name],
                "net_interface": device_type.net_interface,
            }
            if run_name == "raspberrypi4-64":
                context["BOOTLOADER_URL"] = "%sother/u-boot-%s.bin" % (run_url, run_name)
            if run_name == "stm32mp1-disco":
                context["BOOTLOADER_URL"] = "%sother/boot.itb" % (run_url)
            dt_settings = device_type.get_settings()
            for key, value in dt_settings.items():
                try:
                    context.update({key: value.format(run_url=run_url, run_name=run_name)})
                except KeyError:
                    # ignore KeyError in case of misformatted string
                    pass
                except AttributeError:
                    # ignore values that are not strings
                    pass

            lava_job_definition = None
            if not template.get("template", None):
                lava_job_definition = get_template(template["name"]).render(context)
            else:
                lava_job_definition = template["template"].render(context)
            if not lava_job_definition:
                # possibly raise exception
                return
            lava_job_definitions.append(lava_job_definition)

            # submit jobs though qa-reports
            project.squad_backend.submit_lava_job(
                "lmp",
                f"{project.name}",
                f"{gh_git_sha}",
                f"{run_name}",
                lava_job_definition
            )
