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
from urllib.parse import urljoin

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


class Project(models.Model):
    name = models.CharField(max_length=32)
    # secret stored in a factory and passed in webhook
    # request POST header
    secret = models.CharField(max_length=128)
    # private key to sign targets.json for tagging
    privkey = models.TextField(null=True, blank=True)
    # ID corresponding to the privkey
    keyid = models.CharField(max_length=64, null=True, blank=True)
    lava_backend = models.ForeignKey(
        LAVABackend,
        on_delete=models.SET_NULL,
        null=True,
        blank=True)
    squad_backend = models.ForeignKey(
        SQUADBackend,
        on_delete=models.SET_NULL,
        null=True,
        blank=True)
    squad_group = models.CharField(max_length=16, null=True, blank=True)
    create_ota_commit = models.BooleanField(default=False)
    # create commit in containers repository
    # this will trigger a script which should update a file in containers repository
    # for this to work, the file needs to be referenced in Dockerfile
    # only one compose app will be updated
    create_containers_commit = models.BooleanField(default=False)
    compose_app_name = models.CharField(max_length=64, null=True, blank=True)
    compose_app_env_filename = models.CharField(max_length=64, null=True, blank=True)
    default_container_branch = models.CharField(max_length=64, default="master")
    # if set to True, only lmp-manifest merges will trigger testing
    test_on_merge_only = models.BooleanField(default=False)
    qa_reports_project_name = models.CharField(max_length=32, null=True, blank=True)
    el2go_product_id = models.CharField(max_length=32, null=True, blank=True)

    # name of the tag applied to devices and targets
    testing_tag = models.CharField(max_length=16, null=True, blank=True)
    # set to True to apply testing_tag to target
    apply_testing_tag_on_callback = models.BooleanField(default=False)
    # name of the default branch in the lmp-manifest project
    default_branch = models.CharField(max_length=16, default="master")
    # token to allow FoundriesFactory backend operations
    fio_api_token = models.CharField(max_length=40, blank=True, null=True)
    # token to allow source code operations
    fio_repository_token = models.CharField(max_length=40, blank=True, null=True)

    # test plans
    testplans = models.ManyToManyField(TestPlan, blank=True)

    def watch_qa_reports_job(self, build, environment, job_id):
        qa_reports_project_name = self.name
        if self.qa_reports_project_name:
            qa_reports_project_name = self.qa_reports_project_name
        if self.squad_backend:
            build_version = build.build_id
            if build.lmp_commit:
                build_version = build.lmp_commit
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
    # for some builds tests don't need to be scheduled
    # these are builds that are used for update/rollback testing
    schedule_tests = models.BooleanField(default=True)
    # lmp_commit is the head of lmp-manifest tree
    # before commit. It will be used as build version in qa-reports
    lmp_commit = models.CharField(max_length=40, blank=True, null=True)

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
        if self.auto_register_name:
            params = {"factory": self.project.name}
            url = f"https://api.foundries.io/ota/devices/{self.auto_register_name}/"
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
        authentication = self._get_auth_dict()
        if self.auto_register_name:
            params = {"factory": factory}
            url = f"https://api.foundries.io/ota/devices/{self.auto_register_name}/"
            device_remove_request = requests.delete(url, headers=authentication, params=params)
            if device_remove_request.status_code == 200:
                return device_remove_request.json()
            else:
                logger.error(f"Device {self.auto_register_name} deletion failed")
                logger.error(device_remove_request.text)
        return {}

    def _el2go_operation(self, requests_method):
        authentication = self._get_auth_dict()
        if self.el2go_name:
            params = {
                "product-id": self.project.el2go_product_id,
                "devices": [self.el2go_name],
                "production": False
            }
            url = f"https://api.foundries.io/ota/factories/{self.project.name}/el2g/devices/"
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
    JOB_CHOICES = [
        (JOB_LAVA, "Lava"),
        (JOB_OTA, "OTA"),
        (JOB_EL2GO, "EL2GO"),
    ]

    job_type = models.CharField(
        max_length=16,
        choices=JOB_CHOICES,
        default=JOB_LAVA
    )

    def __str__(self):
        return f"{self.job_id} ({self.device})"

