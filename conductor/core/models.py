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
import requests
import yaml
from django.conf import settings
from django.db import models
from django.utils import timezone
from urllib.parse import urljoin


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


class Project(models.Model):
    name = models.CharField(max_length=32)
    # secret stored in a factory and passed in webhook
    # request POST header
    secret = models.CharField(max_length=128)
    lava_url = models.URLField()
    websocket_url = models.URLField(blank=True, null=True)
    lava_api_token = models.CharField(max_length=128)

    def submit_lava_job(self, definition):
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
            return response.json()['job_ids']
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

    def __str__(self):
        return str(self.build_id)


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
        return self.name

    __settings__ = None

    def get_settings(self):
        if self.__settings__ is None:
            self.__settings__ = yaml.safe_load(self.device_type_settings or '') or {}
        return self.__settings__


class LAVADevice(models.Model):
    device_type = models.ForeignKey(LAVADeviceType, on_delete=models.CASCADE)
    name = models.CharField(max_length=32)
    auto_register_name = models.CharField(max_length=64, null=True, blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    pduagent = models.ForeignKey(PDUAgent, null=True, blank=True, on_delete=models.CASCADE)
    # field to record when device was requested to go to maintenance
    # because it's supposed to run OTA job
    ota_started = models.DateTimeField(null=True, blank=True)

    CONTROL_LAVA = "LAVA"
    CONTROL_PDU = "PDU"
    CONTROL_CHOICES = [
        (CONTROL_LAVA, "Lava"),
        (CONTROL_PDU, "PDU")
    ]
    controlled_by = models.CharField(
        max_length=16,
        choices=CONTROL_CHOICES,
        default=CONTROL_LAVA
    )

    def __str__(self):
        return self.name

    def __request_state(self, state):
        auth = {
            "Authorization": f"Token {self.project.lava_api_token}"
        }
        device_url = urljoin(self.project.lava_url, "/".join(["devices", self.name]))
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

    def get_current_target(self):
        # checks the current target reported by FIO API
        token = getattr(settings, "FIO_API_TOKEN", None)
        authentication = {
            "OSF-TOKEN": token,
        }
        if self.auto_register_name:
            url = f"https://api.foundries.io/ota/devices/{self.auto_register_name}/"
            device_details_request = requests.get(url, headers=authentication)
            if device_details_request.status_code == 200:
                return device_details_request.json()
            else:
                logger.error(f"Could not get current target for device {self.pk}")
                logger.error(device_details_request.text)
        return {}

    def remove_from_factory(self):
        token = getattr(settings, "FIO_API_TOKEN", None)
        authentication = {
            "OSF-TOKEN": token,
        }
        if self.auto_register_name:
            url = f"https://api.foundries.io/ota/devices/{self.auto_register_name}/"
            device_remove_request = requests.delete(url, headers=authentication)
            if device_remove_request.status_code == 200:
                return device_remove_request.json()
        return {}


class LAVAJob(models.Model):
    job_id = models.IntegerField()
    # actual device can is filled once LAVA assigns it
    device = models.ForeignKey(LAVADevice, null=True, blank=True, on_delete=models.CASCADE)
    definition = models.TextField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    JOB_LAVA = "LAVA"
    JOB_OTA = "OTA"
    JOB_CHOICES = [
        (JOB_LAVA, "Lava"),
        (JOB_OTA, "OTA")
    ]

    job_type = models.CharField(
        max_length=16,
        choices=JOB_CHOICES,
        default=JOB_LAVA
    )

    def __str__(self):
        return self.job_id

