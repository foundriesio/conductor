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

import logging
import os
import requests
import yaml
from django.conf import settings
from django.db import models
from django.utils import timezone
from http import HTTPStatus
from urllib.parse import urljoin
from requests.exceptions import HTTPError

from conductor.testplan.models import TestPlan

DEFAULT_TIMEOUT=60
logger = logging.getLogger()


def yaml_validator(value):
    if value is None:
        return
    if len(value) == 0:
        return
    try:
        if not isinstance(yaml.safe_load(value), dict):
            raise ValidationError("Dictionary object expected")
    except yaml.YAMLError as e:
        raise ValidationError(e)


class LAVABackend(models.Model):
    name = models.CharField(max_length=32)
    lava_url = models.URLField()
    websocket_url = models.URLField(blank=True, null=True)
    lava_api_token = models.CharField(max_length=128)

    def submit_lava_job(self, definition):
        if not settings.DEBUG_LAVA_SUBMIT:
            # authentication headers
            authentication = {
                "Authorization": "Token %s" % self.lava_api_token,
            }
            response = requests.post(
                urljoin(self.lava_url, "jobs/"),
                headers=authentication,
                data={"definition": definition},
                timeout=DEFAULT_TIMEOUT
            )
            if response.status_code == 201:
                logger.debug(response.text)
                return response.json()['job_ids']
            else:
                logger.info(f"LAVA submission failed with code {response.status_code}")
                logger.info(response.text)
        else:
            # save job definition to file
            y_definition = yaml.safe_load(definition)
            file_name = y_definition.get('device_type') + "_" + y_definition.get('job_name')
            if file_name:
                file_name = file_name.replace(" ", "_") + ".yaml"
            with open(os.path.join(settings.BASE_DIR, file_name), "w") as y_file:
                yaml.dump(y_definition, y_file, default_flow_style=False)
            # return random id list
            return [len(definition)]
        return []

    def __str__(self):
        return self.name


class SQUADBackend(models.Model):
    name = models.CharField(max_length=32)
    squad_url = models.URLField()
    squad_token = models.CharField(max_length=128)

    def watch_lava_job(self,
            group,
            project,
            build,
            environment,
            job_id):
        if not settings.DEBUG_SQUAD_SUBMIT:
            # authentication headers
            authentication = {
                "Auth-Token": self.squad_token,
            }
            return requests.post(
                urljoin(self.squad_url, f"api/watchjob/{group}/{project}/{build}/{environment}"),
                headers=authentication,
                data={"testjob_id": job_id,
                      "backend": self.name},
                timeout=DEFAULT_TIMEOUT
            )
        else:
            from requests.models import Response

            response = Response()
            response.status_code = 201
            response._content = f"{job_id}".encode()
            return response

    def submit_lava_job(self,
            group,
            project,
            build,
            environment,
            job_definition):
        if not settings.DEBUG_SQUAD_SUBMIT:
            # authentication headers
            authentication = {
                "Auth-Token": self.squad_token,
            }
            return requests.post(
                urljoin(self.squad_url, f"api/submitjob/{group}/{project}/{build}/{environment}"),
                headers=authentication,
                data={"definition": job_definition,
                      "backend": self.name},
                timeout=DEFAULT_TIMEOUT
            )
        else:
            from requests.models import Response
            job_id = 123456
            response = Response()
            response.status_code = 201
            response._content = f"{job_id}".encode()
            return response

    def create_build(self,
            group,
            project,
            build,
            patch_source,
            patch_id):
        url_path = f"api/createbuild/{group}/{project}/{build}"
        if not settings.DEBUG_SQUAD_SUBMIT:
            # authentication headers
            authentication = {
                "Auth-Token": self.squad_token,
            }
            data = {}
            if patch_id and patch_source:
                data={"patch_id": patch_id,
                      "patch_source": patch_source}
            return requests.post(
                urljoin(self.squad_url, f"api/createbuild/{group}/{project}/{build}"),
                headers=authentication,
                data=data,
                timeout=DEFAULT_TIMEOUT
            )
        else:
            from requests.models import Response

            job_id = 123456
            response = Response()
            response.status_code = 201
            response._content = f"{job_id}".encode()
            return response

    def update_testjob(self, squad_job_id, name, job_definition):
        if not settings.DEBUG_SQUAD_SUBMIT:
            headers = {
                "Authorization": f"Token {self.squad_token}"
            }
            testjob_api_url = urljoin(self.squad_url, f"api/testjobs/{squad_job_id}")
            job_details_request = requests.get(testjob_api_url, headers=headers)
            if job_details_request.status_code == 200:
                # prepare PUT to update definition
                job_details = job_details_request.json()
                job_details.update({"definition": job_definition, "name": name})
                return requests.put(
                    testjob_api_url,
                    data=job_details,
                    headers=headers
                )
        return None

    def __str__(self):
        return self.name


class Project(models.Model):
    name = models.CharField(
        max_length=32,
        help_text="The name of the Foundries Factory")
    # secret stored in a factory and passed in webhook
    # request POST header
    secret = models.CharField(
        max_length=128,
        help_text="Secret set in the Foundries Factory usign fioctl. The secret is sent by jobserv callback.")
    # private key to sign targets.json for tagging
    privkey = models.TextField(null=True, blank=True, help_text="TUF private key for signing targets")
    # ID corresponding to the privkey
    keyid = models.CharField(max_length=64, null=True, blank=True)
    lava_backend = models.ForeignKey(
        LAVABackend,
        on_delete=models.SET_NULL,
        null=True,
        blank=True)
    # name of the header variable in LAVA inscance
    # the variable is used to authenticate downloads from
    # FoundriesFactory CI
    lava_header = models.CharField(
        max_length=23,
        null=True,
        blank=True,
        help_text="Name of LAVA header created in LAVA profile. Header should be created for the user submitting test jobs")
    squad_backend = models.ForeignKey(
        SQUADBackend,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Name of the SQUAD instance to use for reporing of this project.")
    squad_group = models.CharField(
        max_length=16,
        null=True,
        blank=True,
        help_text="Name of the group in SQUAD instance where this project data is reported. SQUAD project name by default is the same as this project name.")
    create_ota_commit = models.BooleanField(default=False)
    # create commit in containers repository
    # this will trigger a script which should update a file in containers repository
    # for this to work, the file needs to be referenced in Dockerfile
    # only one compose app will be updated
    create_containers_commit = models.BooleanField(
        default=False,
        help_text="If set to true OTA commit will be created in the containers repository")
    compose_app_name = models.CharField(max_length=64, null=True, blank=True)
    compose_app_env_filename = models.CharField(max_length=64, null=True, blank=True)
    default_container_branch = models.CharField(max_length=64, default="master")
    # meta-subscribers branch name
    default_meta_branch = models.CharField(
        max_length=64,
        default="master",
        help_text="Default branch to monitor in meta-subscriber-overrides repository")
    # if set to True, only lmp-manifest merges will trigger testing
    test_on_merge_only = models.BooleanField(
        default=False,
        help_text="If set to true testing will be triggered only on merges from lmp-manifest.")
    qa_reports_project_name = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        help_text="When not empty this name is used as a project name in SQUAD.")
    el2go_product_id = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        help_text="12NC number for the SE05x device. This field will be moved to the LAVADevice. For now all devices in the factory have to use the same SE05x chip.")

    # name of the tag applied to devices and targets
    testing_tag = models.CharField(
        max_length=16,
        null=True,
        blank=True,
        help_text="This tag will be applied to the targets in the Foundries Factory on successful build.")
    # apply testing tag to 1st build only. This is done to prevent OTA
    apply_tag_to_first_build_only = models.BooleanField(
        default=False,
        help_text="When set to true, testing_tag is not applied to the OTA build.")
    # set to True to apply testing_tag to target
    apply_testing_tag_on_callback = models.BooleanField(default=False)
    # produce static deltas for OTA builds
    test_static_delta = models.BooleanField(default=True)
    # name of the default branch in the lmp-manifest project
    default_branch = models.CharField(max_length=16, default="master")
    # token to allow FoundriesFactory backend operations
    fio_api_token = models.CharField(max_length=40, blank=True, null=True)
    # token to allow source code operations
    fio_repository_token = models.CharField(max_length=40, blank=True, null=True)
    # domain of the MEDS instance. If empty defaults to "foundries.io"
    fio_meds_domain = models.CharField(max_length=64, blank=True, null=True)
    # URL of the lmp-manifest repository. This should only be set
    # if the project doesn't directly use FIO lmp-manifest.
    # Example use case is partner factory, i.e. arduino
    fio_lmp_manifest_url = models.URLField(blank=True, null=True)
    # branch in lmp-manifest to merge changes from
    fio_lmp_manifest_branch = models.CharField(max_length=32, blank=True, null=True)
    # update kernel moduel keys for OTA buils
    fio_force_kernel_rebuild = models.BooleanField(default=False)

    # test plans
    testplans = models.ManyToManyField(TestPlan, blank=True)

    def watch_qa_reports_job(self, build, environment, job_id):
        qa_reports_project_name = self.name
        if self.qa_reports_project_name:
            qa_reports_project_name = self.qa_reports_project_name
        if self.squad_backend:
            build_version = build.commit_id
            if build.lmp_commit:
                build_version = build.lmp_commit
            if not build_version:
                build_version = build.build_id
            return self.squad_backend.watch_lava_job(
                    self.squad_group,
                    qa_reports_project_name,
                    build_version,
                    environment,
                    job_id)
        return None

    def submit_lava_job(self, definition):
        if self.lava_backend:
            return self.lava_backend.submit_lava_job(definition)
        return []

    def _retrieve_api_request(self, url, method="get", **kwargs):
        token = self.fio_api_token
        if token is None:
            token = getattr(settings, "FIO_API_TOKEN", None)
        authentication = {
            "OSF-TOKEN": token,
        }
        retries = 3
        retry_codes = [
            HTTPStatus.TOO_MANY_REQUESTS,
            HTTPStatus.INTERNAL_SERVER_ERROR,
            HTTPStatus.BAD_GATEWAY,
            HTTPStatus.SERVICE_UNAVAILABLE,
            HTTPStatus.GATEWAY_TIMEOUT,
        ]

        requests_method = getattr(requests, method)
        call_kwargs = {
            "headers": authentication
        }
        call_kwargs.update(kwargs)

        for n in range(retries):
            try:
                build_request = requests_method(url, **call_kwargs)
                build_request.raise_for_status()
                return build_request.json()
            except HTTPError as exc:
                code = exc.response.status_code
                if code in retry_codes:
                    # retry after n seconds
                    time.sleep(n)
                    continue
                raise

    def get_api_builds(self):
        domain = settings.FIO_DOMAIN
        if self.fio_meds_domain:
            domain = self.fio_meds_domain
        url = f"https://api.{domain}/projects/{self.name}/lmp/builds/"
        if self.name == "lmp":
            # lmp is not a real factory and the URL is different
            url = f"https://api.foundries.io/projects/lmp/builds/"
        return self._retrieve_api_request(url).get("data")

    def ci_build_details(self, ci_id):
        domain = settings.FIO_DOMAIN
        if self.fio_meds_domain:
            domain = self.fio_meds_domain
        url = f"https://api.{domain}/projects/{self.name}/lmp/builds/{ci_id}"
        if self.name == "lmp":
            # lmp is not a real factory and the URL is different
            url = f"https://api.foundries.io/projects/lmp/builds/{ci_id}"
        data = self._retrieve_api_request(url).get("data")
        if data:
            return data.get("build")
        return None

    def create_static_delta(self, from_build_id, to_build_id):
        logger.debug(f"Creating static delta in {self.name} from {from_build_id} to {to_build_id}")
        domain = settings.FIO_DOMAIN
        if self.fio_meds_domain:
            domain = self.fio_meds_domain
        try:
            from_build = self.build_set.get(pk=from_build_id)
            to_build = self.build_set.get(pk=to_build_id)
        except Build.DoesNotExist:
            logger.warning("Build doesn't exist in the database")
            return None

        parameters = {
            "from_versions": [from_build.build_id]
        }
        if not settings.DEBUG_FIO_SUBMIT:
            url = f"https://api.{domain}/ota/factories/{self.name}/targets/{to_build.build_id}/static-deltas/"
            return self._retrieve_api_request(url, method="post", json=parameters)
        else:
            logger.debug("Sending POST to:")
            logger.debug(f"https://api.{domain}/ota/factories/{self.name}/targets/{to_build.build_id}/static-deltas/")
            logger.debug(parameters)
            target_number = to_build.build_id + 1
            return {"jobserv-url": f"https://api.foundries.io/projects/{self.name}/lmp/builds/{target_number}/", "web-url": f"https://ci.foundries.io/projects/{self.name}/lmp/builds/{target_number}"}


    def __str__(self):
        return self.name


class Build(models.Model):
    url = models.URLField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    build_id = models.IntegerField()
    # git sha1 from manifest repository
    # can be empty to ensure backward compatibility
    commit_id = models.CharField(max_length=40, blank=True, null=True)
    # set to True when commit is accompanied with a tag
    # this is filled by task run on regular interval
    is_release = models.BooleanField(default=False)
    # set to True when build was triggered by lmp-manifest merge
    is_merge_commit = models.BooleanField(default=False)
    # keeps track of build branch/tag
    tag = models.CharField(max_length=40, blank=True, null=True)
    # beginning of the commit message subject
    build_reason = models.CharField(max_length=128, blank=True, null=True)
    BUILD_LMP_MANIFEST = "LMP"
    BUILD_META_SUB = "MET"
    BUILD_TRIGGER_CHOICES = [
        (BUILD_LMP_MANIFEST, "LmP Manifest"),
        (BUILD_META_SUB, "Meta Subscriber Overrides"),
    ]
    build_trigger = models.CharField(max_length=3, choices=BUILD_TRIGGER_CHOICES, default=BUILD_LMP_MANIFEST)
    # Build type will replace schedule_tests field
    # It will change how the test schedulling behaves in case of different
    # CI builds. Build type also needs to be taken into account in test jobs
    BUILD_TYPE_REGULAR = "REG"
    BUILD_TYPE_OTA = "OTA"
    BUILD_TYPE_STATIC_DELTA = "SDE"
    BUILD_TYPE_CONTAINERS = "CTR"
    BUILD_TYPE_CHOICES = [
        (BUILD_TYPE_REGULAR, "Ordinary build (manifest or meta-sub)"),
        (BUILD_TYPE_OTA, "OTA build"),
        (BUILD_TYPE_STATIC_DELTA, "Create static delta between targets"),
        (BUILD_TYPE_CONTAINERS, "Containers build"),
    ]
    build_type = models.CharField(max_length=3, choices=BUILD_TYPE_CHOICES, default=BUILD_TYPE_REGULAR)
    # build status that comes from the callback
    # this field is updated any time jobserv callback comes in
    build_status = models.CharField(max_length=16, null=True, blank=True)
    # lmp_commit is the head of lmp-manifest tree
    # before commit. It will be used as build version in qa-reports
    lmp_commit = models.CharField(max_length=40, blank=True, null=True)
    # shit flag is set to true when there is
    # [skip qa] or [skip-qa] string in the commit message
    skip_qa = models.BooleanField(default=False)
    # keeps track of restarts in the build
    restart_counter = models.IntegerField(default=0)
    # static delta build references
    static_from = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name="staticfrom")
    static_to = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name="staticto")

    def __str__(self):
        return f"{self.build_id} ({self.project.name})"

    def generate_context(self, device_type_name):
        # returns testing context for the build.
        run = Run.objects.get(build=self, run_name=device_type_name)
        device_type = self.project.lavadevicetype_set.get(name=device_type_name)
        return {
            "INTERFACE": device_type.net_interface,
            "CONFIG_VALUES": "CONFIG_CGROUPS",
            "OSTREE_HASH": run.ostree_hash,
            "TARGET": f"{self.build_id}",
        }

    def get_lmp_commit_url(self):
        if not self.lmp_commit or self.lmp_commit == self.commit_id:
            return ""
        lmp_manifest = settings.FIO_BASE_MANIFEST
        if self.project.fio_lmp_manifest_url:
            lmp_manifest = self.project.fio_lmp_manifest_url
        return f"{lmp_manifest}/commit/{self.lmp_commit}"

    def get_commit_url(self):
        if not self.commit_id:
            return ""
        domain = settings.FIO_DOMAIN
        if self.project.fio_meds_domain:
            domain = self.project.fio_meds_domain
        if self.build_trigger == Build.BUILD_META_SUB:
            return f"https://source.{domain}/factories/{self.project.name}/meta-subscriber-overrides.git/commit/?id={self.commit_id}"
        return f"https://source.{domain}/factories/{self.project.name}/lmp-manifest.git/commit/?id={self.commit_id}"

    def get_qa_reports_url(self):
        commit = self.commit_id
        if self.lmp_commit:
            commit = self.lmp_commit
        project = self.project.name
        if self.project.qa_reports_project_name:
            project = self.project.qa_reports_project_name
        return f"https://qa-reports.foundries.io/{self.project.squad_group}/{project}/build/{commit}"

    def is_scheduled_tests(self):
        if self.build_type == Build.BUILD_TYPE_REGULAR and not self.skip_qa:
            return True
        return False


class BuildTag(models.Model):
    name = models.CharField(max_length=32)
    builds = models.ManyToManyField(Build)

    def __str__(self):
        return self.name


class Run(models.Model):
    build = models.ForeignKey(Build, on_delete=models.CASCADE)
    device_type = models.CharField(max_length=32)
    ostree_hash = models.CharField(max_length=64)
    run_name = models.CharField(max_length=32)

    def __str__(self):
        return "%s (%s)" % (self.run_name, self.build.build_id)


class PDUAgent(models.Model):
    name = models.CharField(max_length=32)

    STATE_ONLINE = "Online"
    STATE_OFFLINE = "Offline"
    STATE_CHOICES = [
        (STATE_ONLINE, "Online"),
        (STATE_OFFLINE, "Offline")
    ]
    state = models.CharField(
        max_length=16,
        choices=STATE_CHOICES,
        default=STATE_OFFLINE
    )
    last_ping = models.DateTimeField(null=True, blank=True)
    version = models.CharField(max_length=32)
    token = models.CharField(max_length=64)
    message = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class LAVADeviceType(models.Model):
    name = models.CharField(max_length=32)
    # name of the device in the Foundries factory
    ota_name = models.CharField(max_length=64, blank=True, null=True)
    net_interface = models.CharField(max_length=32)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    # keep device type specific settings in the TextField
    device_type_settings = models.TextField(blank=True, null=True, validators=[yaml_validator])
    ARCH_ARMHF = "armhf"
    ARCH_AARCH64 = "aarch64"
    ARCH_AMD64 = "amd64"
    ARCH_CHOICES = [
        (ARCH_ARMHF, "armhf"),
        (ARCH_AARCH64, "aarch64"),
        (ARCH_AMD64, "amd64")
    ]
    architecture = models.CharField(max_length=8, choices=ARCH_CHOICES, default=ARCH_AARCH64)

    def __str__(self):
        return f"{self.name} ({self.project.name})"

    __settings__ = None

    def get_settings(self):
        if self.__settings__ is None:
            self.__settings__ = yaml.safe_load(self.device_type_settings or '') or {}
        return self.__settings__


class LAVADevice(models.Model):
    device_type = models.ForeignKey(LAVADeviceType, on_delete=models.CASCADE)
    name = models.CharField(max_length=32)
    auto_register_name = models.CharField(max_length=64, null=True, blank=True)
    el2go_name = models.CharField(max_length=64, null=True, blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    pduagent = models.ForeignKey(PDUAgent, null=True, blank=True, on_delete=models.CASCADE)
    # field to record when device was requested to go to maintenance
    # because it's supposed to run OTA job
    ota_started = models.DateTimeField(null=True, blank=True)

    CONTROL_LAVA = "LAVA"
    CONTROL_PDU = "PDU"
    # This is like LAVA but tells conductor to call backend el2g_delete and el2g_add functions
    CONTROL_EL2GO = "EL2G"
    CONTROL_CHOICES = [
        (CONTROL_LAVA, "Lava"),
        (CONTROL_PDU, "PDU"),
        (CONTROL_EL2GO, "EL2GO")
    ]
    controlled_by = models.CharField(
        max_length=16,
        choices=CONTROL_CHOICES,
        default=CONTROL_LAVA
    )

    def __str__(self):
        return f"{self.name} ({self.project.name})"

    def __request_state(self, state):
        auth = {
            "Authorization": f"Token {self.project.lava_backend.lava_api_token}"
        }
        device_url = urljoin(self.project.lava_backend.lava_url, "/".join(["devices", self.name]))
        if not device_url.endswith("/"):
            device_url = device_url + "/"
        device_request = requests.get(device_url, headers=auth)
        if device_request.status_code == 200:
            device_json = device_request.json()
            device_json['health'] = state
            logger.info(device_json)
            device_put_request = requests.put(device_url, json=device_json, headers=auth)
            if device_put_request.status_code == 200:
                logger.info(f"Requested state: {state} for device: {self.name}")
                return True
            else:
                logger.warning("LAVA API request rejected")
                logger.warning(device_put_request.status_code)
                logger.warning(device_put_request.text)
        return False

    def request_maintenance(self):
        # send request to LAVA server to change device state to Maintenance
        # this prevents from scheduling more LAVA jobs while the device
        # runs OTA update and tests
        if self.__request_state("Maintenance"):
            self.ota_started = timezone.now()
            self.controlled_by = LAVADevice.CONTROL_PDU
            self.save()

    def request_online(self):
        if self.__request_state("Good"):
            self.controlled_by = LAVADevice.CONTROL_LAVA
            self.save()

    def _get_auth_dict(self):
        token = self.project.fio_api_token
        if token is None:
            token = getattr(settings, "FIO_API_TOKEN", None)
        authentication = {
            "OSF-TOKEN": token,
        }
        return authentication

    def get_current_target(self):
        # checks the current target reported by FIO API
        authentication = self._get_auth_dict()
        domain = settings.FIO_DOMAIN
        if self.project.fio_meds_domain:
            domain = self.project.fio_meds_domain
        if self.auto_register_name:
            params = {"factory": self.project.name}
            url = f"https://api.{domain}/ota/devices/{self.auto_register_name}/"
            device_details_request = requests.get(url, headers=authentication, params=params)
            if device_details_request.status_code == 200:
                return device_details_request.json()
            else:
                logger.error(f"Could not get current target for device {self.pk}")
                logger.error(device_details_request.text)
        return {}

    def remove_from_factory(self, factory=None):
        if not factory:
            logger.error("Factory name is required when removing device")
            return {}
        domain = settings.FIO_DOMAIN
        if self.project.fio_meds_domain:
            domain = self.project.fio_meds_domain
        authentication = self._get_auth_dict()
        if self.auto_register_name:
            params = {"factory": factory}
            url = f"https://api.{domain}/ota/devices/{self.auto_register_name}/"
            device_remove_request = requests.delete(url, headers=authentication, params=params)
            if device_remove_request.status_code == 200:
                return device_remove_request.json()
            else:
                logger.error(f"Device {self.auto_register_name} deletion failed")
                logger.error(device_remove_request.text)
        return {}

    def _el2go_operation(self, requests_method):
        authentication = self._get_auth_dict()
        domain = settings.FIO_DOMAIN
        if self.project.fio_meds_domain:
            domain = self.project.fio_meds_domain
        if self.el2go_name:
            params = {
                "product-id": self.project.el2go_product_id,
                "devices": [self.el2go_name],
                "production": False
            }
            url = f"https://api.{domain}/ota/factories/{self.project.name}/el2g/devices/"
            device_operation_request = requests_method(url, headers=authentication, json=params)
            if device_operation_request.status_code == 200:
                return device_operation_request.json()
            else:
                logger.error(f"Operation {requests_method.__name__} on {self.el2go_name} EL2GO device failed")
                logger.error(f"called URL: {url}")
                logger.error(device_operation_request.text)
        return {}

    def remove_from_el2go(self):
        # DELETE to /ota/factories/{factory}/el2g/devices/
        return self._el2go_operation(requests.delete)

    def add_to_el2go(self):
        # POST to /ota/factories/{factory}/el2g/devices/
        return self._el2go_operation(requests.post)


class LAVAJob(models.Model):
    job_id = models.IntegerField()
    # actual device can is filled once LAVA assigns it
    device = models.ForeignKey(LAVADevice, null=True, blank=True, on_delete=models.CASCADE)
    definition = models.TextField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    JOB_LAVA = "LAVA"
    JOB_EL2GO = "EL2GO"
    JOB_OTA = "OTA"
    JOB_ASSEMBLE = "ASM"
    JOB_CHOICES = [
        (JOB_LAVA, "Lava"),
        (JOB_OTA, "OTA"),
        (JOB_EL2GO, "EL2GO"),
        (JOB_ASSEMBLE, "Assemble"),
    ]

    job_type = models.CharField(
        max_length=16,
        choices=JOB_CHOICES,
        default=JOB_LAVA
    )

    def __str__(self):
        return f"{self.job_id} ({self.device})"

