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

import requests
import yaml
from django.db import models
from urllib.parse import urljoin


DEFAULT_TIMEOUT=60


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
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    pduagent = models.ForeignKey(PDUAgent, null=True, blank=True, on_delete=models.CASCADE)

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


class LAVAJob(models.Model):
    job_id = models.IntegerField()
    # actual device can is filled once LAVA assigns it
    device = models.ForeignKey(LAVADevice, null=True, blank=True, on_delete=models.CASCADE)
    definition = models.TextField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE)

    def __str__(self):
        return self.job_id

