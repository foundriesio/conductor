# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

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
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.backends import default_backend

from conductor.celery import app as celery
from celery import chain, group
from celery.signals import task_internal_error, task_failure
from celery.utils.log import get_task_logger
from conductor.core.models import Run, Build, BuildTag, LAVADeviceType, LAVADevice, LAVAJob, Project
from conductor.testplan.models import TestPlan, TestJob
from conductor.utils import template_from_string, prepare_context
from datetime import timedelta
from django.conf import settings
from django.core.mail import mail_admins
from django.db import transaction
from django.template.loader import get_template
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


def task_email_notify(sender=None, headers=None, body=None, **kwargs):
    import socket
    kwargs['sender'] = sender
    subject = "Error: Task {sender.name} ({task_id})".format(**kwargs)
    try:
        subject = "Error: Task {sender.name} ({task_id}): {exception.context} {exception.problem}".format(**kwargs)
    except AttributeError:
        pass
    message = """Task {sender.name} with id {task_id} raised exception:
{exception!r}
Task was called with args: {args}
kwargs: {kwargs}.
The contents of the full traceback was:
{einfo}
    """.format(**kwargs)
    mail_admins(subject, message)


# record notification for failed and error tasks
task_failure.connect(task_email_notify)
task_internal_error.connect(task_email_notify)


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


def restart_ci_run(project, run_url):
    token = project.fio_api_token
    if token is None:
        token = getattr(settings, "FIO_API_TOKEN", None)
    authentication = {
        "OSF-TOKEN": token,
    }
    url = run_url + "rerun"
    post_request = requests.post(url, headers=authentication)
    if post_request.status_code == 200:
        if post_request.json().get("status") == "success":
            return True
    return False


def _get_ci_url(url, project):
    token = project.fio_api_token
    if token is None:
        token = getattr(settings, "FIO_API_TOKEN", None)
    authentication = {
        "OSF-TOKEN": token,
    }
    session = requests.Session()
    session.headers.update(authentication)
    url_request = requests_retry_session(session=session).get(url)
    if url_request.status_code == 200:
        return url_request.text.strip()
    return None


def _get_os_tree_hash(url, project):
    logger.debug("Retrieving ostree hash with base url: %s" % url)
    ostree_url = urljoin(url, "other/ostree.sha.txt")
    return _get_ci_url(ostree_url, project)


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
    sig = None
    if isinstance(key, Ed25519PrivateKey):
        meta["signatures"][0]["method"] = "ed25519"
        sig = key.sign(
            canonical,
        )
    if isinstance(key, RSAPrivateKey):
        meta["signatures"][0]["method"] = "rsassa-pss-sha256"
        sig = key.sign(
            canonical,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
            hashes.SHA256(),
        )
    if sig is None:
        logger.error("targets.json is not signed.")
        return
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


def _retrieve_previous_build(
        build,
        build_types=[Build.BUILD_TYPE_REGULAR,
                     Build.BUILD_TYPE_OTA,
                     Build.BUILD_TYPE_STATIC_DELTA,
                     Build.BUILD_TYPE_CONTAINERS]):

    previous_builds = build.project.build_set.filter(
            build_id__lt=build.build_id,
            tag=build.tag,
            build_type__in=build_types).order_by('-build_id')
    previous_build = None
    if previous_builds:
        previous_build = previous_builds[0]
    return previous_build


@celery.task(bind=True)
def restart_failed_runs(self, build_id, request_json):
    # restarts failed runs in a build
    # only restarts when detected infrastructure issue
    # genuine build failures should not be restarted
    restarted = False
    try:
        build = Build.objects.get(pk=build_id)
    except Build.DoesNotExist:
        logger.error(f"No Build with ID {build_id} for failed CI job.")
        return
    for run in request_json.get("runs"):
        if run.get("status") != "PASSED":
            # restart the run
            if build.restart_counter < settings.MAX_BUILD_RESTARTS and build.project.restart_failed_builds:
                if restart_ci_run(build.project, run.get("url")):
                    restarted = True
    if restarted:
        build.restart_counter = build.restart_counter + 1
        build.save()


@celery.task(bind=True)
def tag_build_runs(self, build_id):
    logger.debug("Received tagging task for build: %s" % build_id)
    build = None
    try:
        build = Build.objects.get(pk=build_id)
    except Build.DoesNotExist:
        return None

    if build.skip_qa:
        logger.debug("Skipping testing. [skip qa] found in commit message")
        return None

    if not build.project.apply_testing_tag_on_callback:
        logger.info(f"Not setting tag on build {build}. Disabled in project settings")
        return None

    if not build.project.testing_tag:
        logger.debug("Nothing to do as project doesn't have testing tag")
        return None

    if build.build_reason and \
            settings.FIO_UPGRADE_ROLLBACK_MESSAGE in build.build_reason and \
            build.project.apply_tag_to_first_build_only:
        logger.debug("Nothing to do as tag only applies to 1st build")
        logger.debug("This is OTA build")
        return None

    testing_buildtag, _ = BuildTag.objects.get_or_create(name=build.project.testing_tag)

    previous_build = _retrieve_previous_build(build)
    old_tagged_builds = []
    if previous_build:
        old_tagged_builds = build.project.build_set.filter(buildtag=testing_buildtag, build_id__lt=previous_build.build_id)
        # there should only be 2 tagged builds: current and previous

    # remove tags from old builds
    for old_tagged_build in old_tagged_builds:
        _remove_tag(old_tagged_build, testing_buildtag)

    # tag current build
    _add_tag(build, testing_buildtag)
    return None


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

    if build.skip_qa:
        logger.debug("Skipping testing. [skip qa] found in commit message")
        return None

    if not build.is_merge_commit and build.build_type == Build.BUILD_TYPE_REGULAR and build.project.test_on_merge_only:
        # don't schedule tests
        return None
    # previous build has to be a platform build
    # this is important for container build tests
    previous_build = _retrieve_previous_build(build, build_types=[Build.BUILD_TYPE_REGULAR, Build.BUILD_TYPE_OTA])
    device_type = None
    try:
        device_type = LAVADeviceType.objects.get(name=run_name, project=build.project)
    except LAVADeviceType.DoesNotExist:
        logger.debug(f"Device type {run_name} not found for {build.project}")
        return None

    templates = []
    downgrade_templates = []
    # if there is a TestPlan object defined for the Project
    # use it to generate templates. Otherwise use the static rules
    # below
    if build.project.testplans.all():
        for plan in build.project.testplans.filter(lava_device_type=run_name):
            if build.build_reason and build.build_type == Build.BUILD_TYPE_REGULAR:
                for plan_testjob in plan.testjobs.filter(is_ota_job=False, is_static_delta_job=False):
                    job_type = LAVAJob.JOB_LAVA
                    if plan_testjob.is_el2go_job:
                        job_type = LAVAJob.JOB_EL2GO
                    templates.append({
                        "name": plan_testjob.name,
                        "job_type": job_type,
                        "build": build,
                        "template": template_from_string(yaml.dump(plan_testjob.get_job_definition(plan), default_flow_style=False))
                    })
            if build.build_reason and build.build_type in [Build.BUILD_TYPE_OTA, Build.BUILD_TYPE_CONTAINERS]:
                for plan_testjob in plan.testjobs.filter(is_ota_job=True, is_downgrade_job=False, is_static_delta_job=False):
                    job_type = LAVAJob.JOB_LAVA
                    if plan_testjob.is_el2go_job:
                        job_type = LAVAJob.JOB_EL2GO
                    templates.append({
                        "name": plan_testjob.name,
                        "job_type": job_type,
                        "build": previous_build,
                        "template": template_from_string(yaml.dump(plan_testjob.get_job_definition(plan), default_flow_style=False))
                    })
                for plan_testjob in plan.testjobs.filter(is_ota_job=True, is_downgrade_job=True, is_static_delta_job=False):
                    job_type = LAVAJob.JOB_LAVA
                    if plan_testjob.is_el2go_job:
                        job_type = LAVAJob.JOB_EL2GO
                    downgrade_templates.append({
                        "name": plan_testjob.name,
                        "job_type": job_type,
                        "build": build,
                        "template": template_from_string(yaml.dump(plan_testjob.get_job_definition(plan), default_flow_style=False))
                    })
            if build.build_reason and build.build_type in [Build.BUILD_TYPE_CONTAINERS]:
                for plan_testjob in plan.testjobs.filter(is_assemble_image_job=True):
                    templates.append({
                        "name": plan_testjob.name,
                        "job_type": LAVAJob.JOB_ASSEMBLE,
                        "build": build,
                        "template": template_from_string(yaml.dump(plan_testjob.get_job_definition(plan), default_flow_style=False))
                    })

    else:
        logger.info("Default test plan disabled")

    logger.debug(f"run_name: {run_name}")
    logger.debug(f"{templates}")
    lava_templates = _submit_lava_templates(templates, build, device_type, submit_jobs)
    lava_templates_downgrade = []
    if previous_build and downgrade_templates:
        logger.debug(f"downgrade")
        logger.debug(f"{downgrade_templates}")
        lava_templates_downgrade = _submit_lava_templates(downgrade_templates, previous_build, device_type, submit_jobs)
    return lava_templates + lava_templates_downgrade


def _submit_lava_templates(templates, build, device_type, submit_jobs, watch_jobs=True, ostree_hash_empty=False):
    run_name = device_type.name
    lava_job_definitions = []
    lava_header = settings.FIO_LAVA_HEADER
    if build.project.lava_header:
        lava_header = build.project.lava_header
    for template in templates:
        lcl_build = template.get("build")
        if not lcl_build:
            continue
        run_url = f"{lcl_build.url}runs/{run_name}/"
        if template.get("job_type") == LAVAJob.JOB_ASSEMBLE:
            # assume assemble system image is enabled in the factory
            previous_build = _retrieve_previous_build(build, build_types=[Build.BUILD_TYPE_REGULAR])
            run_url = f"{previous_build.url}runs/{run_name}/"
        ostree_hash=_get_os_tree_hash(run_url, build.project)
        if not ostree_hash:
            # ostree hash doesn't exist for base console image builds
            logger.warning("OSTree hash missing")
            if not ostree_hash_empty:
                continue

        # try to find LMP build corresponding to this build
        trigger = None
        if lcl_build.lmp_commit:
            try:
                lmp_build = Build.objects.get(project__name="lmp", commit_id=lcl_build.lmp_commit)
                trigger = lmp_build.url
            except Build.DoesNotExist:
                logger.info(f"LMP build with commit: {lcl_build.lmp_commit} NOT FOUND")

        run, _ = Run.objects.get_or_create(
            build=lcl_build,
            device_type=device_type,
            ostree_hash=ostree_hash,
            run_name=run_name
        )

        context = prepare_context(run_name, run_url, lcl_build.url, lcl_build.build_id)
        context.update({
            "build_commit": lcl_build.commit_id,
            "build_reason": lcl_build.build_reason,
            "trigger": trigger,

            "LAVA_HEADER": lava_header,
            "MFGTOOL_URL": f"{lcl_build.url}runs/{run_name}-mfgtools/mfgtool-files.tar.gz",
            "MFGTOOL_BUILD_URL": f"{lcl_build.url}runs/{run_name}-mfgtools/",

            "net_interface": device_type.net_interface,
            "os_tree_hash": run.ostree_hash,
            "target": lcl_build.build_id,
            "ota_target": build.build_id,
            "factory": build.project.name,
        })
        if lcl_build.lmp_commit:
            context.update(
                {"lmp_commit": lcl_build.lmp_commit,
                 "lmp_commit_url": lcl_build.get_lmp_commit_url()
                }
            )
        dt_settings = device_type.get_settings()
        for key, value in dt_settings.items():
            try:
                context.update({key: value.format(**context)})
            except KeyError:
                # ignore KeyError in case of misformatted string
                pass
            except AttributeError:
                # ignore values that are not strings
                pass
        if template.get("job_type") == LAVAJob.JOB_ASSEMBLE:
            # IMAGE_URL has to be overwritten here for assemble jobs
            context["IMAGE_URL"] = f"{lcl_build.url}runs/assemble-system-image/{build.tag}/lmp-factory-image-{run_name}.wic.gz"
            context["MFGTOOL_URL"] = f"{previous_build.url}runs/{run_name}-mfgtools/mfgtool-files.tar.gz"
            context["MFGTOOL_BUILD_URL"] = f"{previous_build.url}runs/{run_name}-mfgtools/"
            context.update(
                {"lmp_commit": previous_build.lmp_commit,
                 "lmp_commit_url": previous_build.get_lmp_commit_url()
                }
            )
            lcl_build = previous_build

        lava_job_definition = None
        if not template.get("template", None):
            lava_job_definition = get_template(template["name"]).render(context)
        else:
            lava_job_definition = template["template"].render(context)
        if not lava_job_definition:
            # possibly raise exception
            logger.debug("LAVA test deifinition missing")
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
                requested_device_type=device_type,
                project=build.project,
                job_type=job_type,
            )
            if watch_jobs:
                if job_type in [LAVAJob.JOB_LAVA, LAVAJob.JOB_EL2GO, LAVAJob.JOB_ASSEMBLE]:
                    # returns HTTPResponse object or None
                    watch_response = build.project.watch_qa_reports_job(lcl_build, run_name, job)
                    if watch_response and watch_response.status_code == 201:
                        # update the testjob object in SQUAD
                        squad_job_id = watch_response.text
                        job_definition_yaml = yaml.safe_load(lava_job_definition)
                        job_name = job_definition_yaml.get('job_name')
                        build.project.squad_backend.update_testjob(squad_job_id, job_name, lava_job_definition)
    return lava_job_definitions


@celery.task(bind=True)
def submit_single_testjob(self, project_id, build_id, testplan_id, testjob_id):
    project = Project.objects.get(pk=project_id)
    build = Build.objects.get(pk=build_id)
    testjob = TestJob.objects.get(pk=testjob_id)
    testplan = TestPlan.objects.get(pk=testplan_id)
    device_type = LAVADeviceType.objects.get(name=testplan.lava_device_type, project=build.project)
    job_type = LAVAJob.JOB_LAVA
    if testjob.is_el2go_job:
        job_type = LAVAJob.JOB_EL2GO
    if testjob.is_assemble_image_job:
        job_type = LAVAJob.JOB_ASSEMBLE

    templates = []
    if build.build_reason:
        templates.append({
            "name": testjob.name,
            "job_type": job_type,
            "build": build,
            "template": template_from_string(yaml.dump(testjob.get_job_definition(testplan), default_flow_style=False))
        })
    logger.debug(templates)
    _submit_lava_templates(templates, build, device_type, True, False, True)


@celery.task(bind=True)
def poll_static_delta_build(self, build_id):
    build = None
    try:
        build = Build.objects.get(pk=build_id)
    except Build.DoesNotExist:
        return None

    # poll build_url and check if status == PASSED
    build_json = build.project.ci_build_details(build.build_id)
    if build_json.get("status") == "PASSED":
        schedule_static_delta(build.pk)
    elif build_json.get("status") == "FAILED":
        return None
    else:
        # repeat the task every 2 minutes
        poll_static_delta_build.apply_async(args=[build_id], countdown=120)
    return True


@celery.task(bind=True)
def create_static_delta_build(self, build_id):
    build = None
    try:
        build = Build.objects.get(pk=build_id)
    except Build.DoesNotExist:
        return None

    previous_build = _retrieve_previous_build(build, build_types=[Build.BUILD_TYPE_REGULAR, Build.BUILD_TYPE_OTA])
    if not previous_build:
        # no previous build found
        return None
    # create static delta CI build from previous_build to build
    result_json = build.project.create_static_delta(previous_build.id, build.id)
    # {"jobserv-url": "https://api.foundries.io/projects/milosz-rpi3/lmp/builds/581/", "web-url": "https://ci.foundries.io/projects/milosz-rpi3/lmp/builds/581"}
    build_url = result_json.get("jobserv-url")
    s_build, _ = Build.objects.get_or_create(
        url=build_url,
        project=build.project,
        build_id=build_url.rsplit("/", 2)[1],  # assuming url ends with /
        tag=None,
        build_type=Build.BUILD_TYPE_STATIC_DELTA,
        static_from=previous_build,
        static_to=build)

    poll_static_delta_build.apply_async(args=[s_build.id], countdown=120)


@celery.task(bind=True)
def schedule_static_delta(self, build_id):
    build = None
    try:
        build = Build.objects.get(pk=build_id)
    except Build.DoesNotExist:
        return None
    # build.static_from - original build from git change
    # build.static_to - OTA build created by conductor
    # tests should be scheduled with static_from for flashing and static_to as final target
    # static delta build doesn't have MACHINE specific runs.
    # let's use static_from runs to determine the MACHINES
    if not build.static_from:
        return None
    if build.static_from.skip_qa:
        # don't schedule any tests
        return None
    for run in build.static_from.run_set.all():
        templates = []
        device_type = None
        try:
            device_type = build.project.lavadevicetype_set.get(name=run.run_name)
        except LAVADeviceType.DoesNotExist:
            logger.warning(f"No device type {run.device_type} in project {build.project}")
            continue
        for plan in build.project.testplans.filter(lava_device_type=run.run_name):
            for plan_testjob in plan.testjobs.filter(is_static_delta_job=True):
                job_type = LAVAJob.JOB_LAVA
                if plan_testjob.is_el2go_job:
                    job_type = LAVAJob.JOB_EL2GO
                templates.append({
                    "name": plan_testjob.name,
                    "job_type": job_type,
                    "build": build.static_from,
                    "template": template_from_string(yaml.dump(plan_testjob.get_job_definition(plan), default_flow_style=False))
                })
        _submit_lava_templates(templates, build.static_to, device_type, True)


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
                for skip_message in settings.SKIP_QA_MESSAGES:
                    if skip_message in commit.message:
                        build.skip_qa = True
                if len(commit.parents) > 1:
                    build.is_merge_commit = True
                    # this is merge commit
                    for parent in commit.parents:
                        if parent.hexsha == old_commit.hexsha:
                            # this is previous HEAD
                            continue
                        build.lmp_commit = parent.hexsha
            except ValueError:
                # commit was not found in the repository
                # this usually means build was triggered from meta-sub
                if build.project.default_meta_branch:
                    meta_repository_path = os.path.join(settings.FIO_REPOSITORY_META_HOME, build.project.name)
                    meta_repository = Repo(meta_repository_path)
                    old_meta_commit = meta_repository.commit("HEAD")
                    # there should only be one remote in this repository
                    remote = meta_repository.remote(name="origin")
                    remote.fetch()
                    meta_repository.git.reset("--hard", f"origin/{build.project.default_meta_branch}")
                    try:
                        meta_commit = meta_repository.commit(rev=build.commit_id)
                        logger.debug(f"Meta Commit: {build.commit_id}")
                        logger.debug(f"Commit message: {meta_commit.message}")
                        build.build_reason = meta_commit.message[:127]
                        build.build_trigger = Build.BUILD_META_SUB
                        for skip_message in settings.SKIP_QA_MESSAGES:
                            if skip_message in meta_commit.message:
                                build.skip_qa = True
                    except ValueError:
                        build.build_reason = "Trigerred from unknown source"
                else:
                    build.build_reason = "Trigerred from meta-sub"

            if settings.FIO_UPGRADE_ROLLBACK_MESSAGE in build.build_reason:
                build.build_type = Build.BUILD_TYPE_OTA
            else:
                if build.project.apply_tag_to_first_build_only:
                    # apply tags to 1st build
                    # this action depends on other project settings
                    tag_build_runs.delay(build.pk)

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
            commit_id = run_json['env'].get('GIT_SHA')
            build.commit_id = commit_id
            build.save()
            _update_build_reason(build)
            build.refresh_from_db()
            if build.skip_qa:
                logger.debug("Skipping testing. [skip qa] found in commit message")
                return None

            if build.build_type in [Build.BUILD_TYPE_REGULAR, Build.BUILD_TYPE_OTA]:
                if settings.FIO_UPGRADE_ROLLBACK_MESSAGE not in build.build_reason:
                    create_upgrade_commit.delay(build_id)
                else:
                    # create static delta for OTA build and it's previous build
                    create_static_delta_build.delay(build_id)
            if build.build_type == Build.BUILD_TYPE_CONTAINERS:
                # do nothing for containers for now
                return None


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
        if project.fio_force_kernel_rebuild:
            cmd.append("-k")
            cmd.append("true")
    if not settings.DEBUG_FIO_SUBMIT and cmd:
        logger.debug(f"{cmd}")
        try:
            subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError:
            mail_admins(
                f"create_upgrade_commit {project} failed",
                f"{e.stdout.decode()}\n\n{e.stderr.decode()}"
            )
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
        logger.warning("Project does not exist")
        return
    # check if repository DIR already exists
    repository_path = os.path.join(settings.FIO_REPOSITORY_HOME, project.name)
    if not __project_repository_exists(project):
        # create repository DIR
        os.makedirs(repository_path)
    domain = settings.FIO_DOMAIN
    if project.fio_meds_domain is not None:
        domain = project.fio_meds_domain
    repository_base = settings.FIO_REPOSITORY_BASE % domain
    lmp_manifest = settings.FIO_BASE_MANIFEST
    if project.fio_lmp_manifest_url:
        lmp_manifest = project.fio_lmp_manifest_url
    # call shell script to clone and configure repository
    cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "checkout_repository.sh"),
           "-d", repository_path,
           "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
           "-u", "%s/%s/lmp-manifest.git" % (repository_base, project.name),
           "-l", settings.FIO_BASE_REMOTE_NAME,
           "-w", lmp_manifest,
           "-t", fio_repository_token,
           "-b", project.default_branch,
           "-D", domain]
    if settings.DEBUG_REPOSITORY_SCRIPTS:
        cmd = cmd + ["-f", str(settings.DEBUG_REPOSITORY_SCRIPTS)]
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
        logger.warning("Project does not exist")
        return
    # check if repository DIR already exists
    repository_path = os.path.join(settings.FIO_REPOSITORY_CONTAINERS_HOME, project.name)
    if not __project_repository_exists(project, settings.FIO_REPOSITORY_CONTAINERS_HOME):
        # create repository DIR
        os.makedirs(repository_path)
    domain = settings.FIO_DOMAIN
    if project.fio_meds_domain is not None:
        domain = project.fio_meds_domain
    repository_base = settings.FIO_REPOSITORY_BASE % domain
    # call shell script to clone and configure repository
    cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "checkout_repository.sh"),
           "-d", repository_path,
           "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
           "-u", "%s/%s/containers.git" % (repository_base, project.name),
           "-t", fio_repository_token,
           "-b", project.default_container_branch,
           "-D", domain,
           "-c", "containers"]
    if settings.DEBUG_REPOSITORY_SCRIPTS:
        cmd = cmd + ["-f", str(settings.DEBUG_REPOSITORY_SCRIPTS)]
    logger.debug("Calling repository creation script")
    logger.debug(" ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        pass

@celery.task
def create_project_meta_repository(project_id):
    project = None
    try:
        project = Project.objects.get(pk=project_id)
        fio_repository_token = project.fio_repository_token
        if not fio_repository_token:
            fio_repository_token = settings.FIO_REPOSITORY_TOKEN
    except Project.DoesNotExist:
        # do nothing if project is not found
        logger.warning("Project does not exist")
        return
    # check if repository DIR already exists
    repository_path = os.path.join(settings.FIO_REPOSITORY_META_HOME, project.name)
    if not __project_repository_exists(project, settings.FIO_REPOSITORY_META_HOME):
        # create repository DIR
        os.makedirs(repository_path)
    domain = settings.FIO_DOMAIN
    if project.fio_meds_domain is not None:
        domain = project.fio_meds_domain
    repository_base = settings.FIO_REPOSITORY_BASE % domain
    # call shell script to clone and configure repository
    cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "checkout_repository.sh"),
           "-d", repository_path,
           "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
           "-u", "%s/%s/meta-subscriber-overrides.git" % (repository_base, project.name),
           "-t", fio_repository_token,
           "-b", project.default_meta_branch,
           "-D", domain,
           "-c", "meta"]
    if settings.DEBUG_REPOSITORY_SCRIPTS:
        cmd = cmd + ["-f", str(settings.DEBUG_REPOSITORY_SCRIPTS)]
    logger.debug("Calling repository creation script")
    logger.debug(" ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        pass


@celery.task
def merge_project_lmp_manifest(project_id):
    project = None
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        logger.error(f"Project with ID {project_id} doesn't exist")
        return
    if project:
        repository_path = os.path.join(settings.FIO_REPOSITORY_HOME, project.name)
        if not __project_repository_exists(project):
            # ignore project with no repository
            return
        # call shell script to merge manifests
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX,"merge_manifest.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-l", settings.FIO_BASE_REMOTE_NAME,
               "-b", project.default_branch]
        if project.fio_lmp_manifest_branch:
            cmd.append("-t")
            cmd.append(project.fio_lmp_manifest_branch)
        logger.info("Calling merge_manifest.sh script")
        logger.info(" ".join(cmd))
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            mail_admins(
                f"merge_project_lmp_manifest {project} failed",
                f"{e.stdout.decode()}\n\n{e.stderr.decode()}"
            )


@celery.task
def merge_lmp_manifest():
    # merge LmP manifest into all project manifest repositories
    # don't touch LmP manifest itself. Project named 'lmp' is
    # a fake project that only keeps the API password.
    # exclude partner factory projects
    projects = Project.objects.filter(fio_lmp_manifest_url__isnull=True, is_parent_factory=False, disabled=False).exclude(name="lmp")
    for project in projects:
        merge_project_lmp_manifest(project.id)


#@celery.task
#def check_build_release():
#    # this task should run once or twice a day
#    # it fills in Build.is_release field based on the repository tags
#    pass


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


def _find_lava_device(lava_job, device_name, project):
    lava_devices = LAVADevice.objects.filter(name=device_name, project=project, device_type=lava_job.requested_device_type)
    # find prompts
    # prompt should correspond to the MACHINE name from OE build
    definition = yaml.safe_load(lava_job.definition)
    if definition is None:
        return None
    for action in definition.get("actions"):
        if "boot" in action.keys():
            boot_action = action.get("boot")
            if boot_action is None:
                return None
            selected_prompt = None
            for prompt in boot_action.get("prompts"):
                if "@" in prompt:
                    selected_prompt = prompt.split("@")[1]
                    break
            for device in lava_devices:
                if device.auto_register_name and selected_prompt in device.auto_register_name:
                    return device
    return None


@celery.task
def process_testjob_notification(event_data):
    job_id = event_data.get("job")
    job_state = event_data.get("state")
    try:
        lava_job = LAVAJob.objects.get(job_id=job_id)
        lava_job.status = job_state
        lava_job.save()
        device_name = event_data.get("device")
        lava_db_device = None
        logger.debug(f"Processing job: {job_id}")
        logger.debug(f"LAVA device name: {device_name}")
        if device_name:
            lava_db_device = _find_lava_device(lava_job, device_name, lava_job.project)
            if lava_db_device is None:
                logger.warning(f"Device from {job_id} not found in {lava_job.project}")
                return
            lava_job.device = lava_db_device
            lava_job.save()
            logger.debug(f"LAVA device is: {lava_db_device.id}")
        if lava_job.job_type == LAVAJob.JOB_LAVA and \
                event_data.get("state") == "Running" and \
                lava_db_device:
            # remove device from factory so it can autoregister
            # and update it's target ID
            logger.info(f"Removing {lava_db_device} from Factory {lava_db_device.project.name}")
            lava_db_device.remove_from_factory(factory=lava_job.project.name)
        if lava_job.job_type == LAVAJob.JOB_EL2GO and \
                event_data.get("state") == "Running" and \
                lava_db_device:
            # remove device from factory so it can autoregister
            # and update it's target ID
            logger.info(f"Removing {lava_db_device} from Factory")
            lava_db_device.remove_from_factory(factory=lava_job.project.name)
            # remove from EL2GO in case it's been added manually
            logger.info(f"LAVA device {lava_db_device} details:")
            logger.info(f"{lava_db_device.project.name}")
            logger.info(f"{lava_db_device.project.el2go_product_id}")
            logger.info(f"{lava_db_device.el2go_name}")
            logger.info(f"Removing {lava_db_device} from EL2GO")
            lava_db_device.remove_from_el2go()
            # add 2 EL2GO so the device can retrieve credentials
            logger.info(f"Adding {lava_db_device} to EL2GO")
            lava_db_device.add_to_el2go()
        if lava_job.job_type == LAVAJob.JOB_EL2GO and \
                event_data.get("state") == "Finished" and \
                lava_db_device:
            # remove EL2GO so the device can retrieve credentials
            # in the next job
            logger.info(f"LAVA device {lava_db_device} details:")
            logger.info(f"{lava_db_device.project.name}")
            logger.info(f"{lava_db_device.project.el2go_product_id}")
            logger.info(f"{lava_db_device.el2go_name}")
            logger.info(f"Removing {lava_db_device} from EL2GO")
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


@celery.task
def fetch_lmp_code_review():
    # this is a periodic task that will fetch list of builds from
    # lmp "factory" and schedule PR tests if the build was started
    # by Github PR
    project = Project.objects.get(name="lmp")
    # get last 25 builds
    api_builds = []
    try:
        builds = project.get_api_builds()
        api_builds = builds.get("builds")
    except:
        # should be HTTP error code
        return
    last_db_build = project.build_set.last()
    if last_db_build and last_db_build.build_id >= api_builds[0]["build_id"]:
        # all builds already fetched
        # do nothing
        return
    for api_build in reversed(api_builds):
        if last_db_build is None or \
                api_build.get("build_id") > last_db_build.build_id:
            # create new builds in DB
            if api_build.get("status") not in ["RUNNING", "RUNNING_WITH_FAILURES", "PROMOTED", "QUEUED"]:
                # only create build object for completed builds
                build_type = Build.BUILD_TYPE_REGULAR
                if api_build.get("trigger_name") == "Code Review":
                    build_type = Build.BUILD_TYPE_CODE_REVIEW
                b = Build.objects.create(
                    url=api_build.get("url"),
                    project=project,
                    build_id=api_build.get("build_id"),
                    build_type=build_type,
                    build_status=api_build.get("status")
                )
                # retrieve build details
                build_description = project.ci_build_details(b.build_id)
                build_reason = build_description.get("reason")
                if build_reason:
                    b.build_reason = build_reason[:127]
                    b.save()
                # fetch commit id from first run
                run = build_description.get("runs")[0]
                run_url = run.get("run_url")
                update_build_commit_id.delay(b.pk, run_url)

                if build_type == Build.BUILD_TYPE_CODE_REVIEW and \
                        api_build.get("status") == "PASSED":
                    schedule_lmp_pr_tests.delay(build_description)

@celery.task
def schedule_project_test_round(build_id):
    build = None
    try:
        build = Build.objects.get(pk=build_id)
    except Build.DoesNotExist:
        return
    logger.debug(f"Schedulling tests for {build}")
    run_url = None
    build_run_list = []
    dev_names = []
    for run in build.run_set.all():
        run_url = run.get_url()
        run_name = run.run_name
        if build.build_type == Build.BUILD_TYPE_CONTAINERS:
            # create run_name list base ond device type
            # architectures
            # container build names are in form "build-architecture"
            if "-" in run_name:
                arch_name = run_name.split("-", 1)[1]
                device_types = LAVADeviceType.objects.filter(project=build.project, architecture=arch_name)
                for dev_type in device_types:
                    dev_names.append(dev_type.name)
            else:
                continue
        else:
            dev_names.append(run_name)
    for dev_name in dev_names:
        build_run_list.append(create_build_run.si(build.pk, dev_name))
    logger.debug(f"RUN URL: {run_url}")
    if run_url is not None:
        # only call update_build_commit_id once as
        # all runs should contain identical GIT_SHA
        logger.debug("Creating test round tasks")
        workflow = (update_build_commit_id.si(build.pk, run_url)| tag_build_runs.si(build.pk) | group(build_run_list))
        workflow.delay()

@celery.task
def schedule_lmp_pr_tests(lmp_build_description):
    if lmp_build_description is None:
        return
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
                    for label in data["labels"]:
                        if label["name"] in settings.SKIP_QA_MESSAGES:
                            logger.info("Skipping testing. %s label found", label["name"])
                            return
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
                        "template": template_from_string(yaml.dump(plan_testjob.get_job_definition(plan), default_flow_style=False))
                    })
        else:
            logger.info("Default test plan disabled")

        logger.debug(f"run_name: {run_name}")
        logger.debug(f"{templates}")
        lava_job_definitions = []
        for template in templates:
            run_url = run.get("url")
            context = prepare_context(run_name, run_url, build_url, build_id)

            context.update({
                "build_commit": gh_git_sha,
                "build_reason": reason,
                "net_interface": device_type.net_interface,
            })
            dt_settings = device_type.get_settings()
            for key, value in dt_settings.items():
                try:
                    context.update({key: value.format(**context)})
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
