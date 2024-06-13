# Copyright 2022 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

import logging
import yaml
from django.db import models
from polymorphic.models import PolymorphicModel
from sortedm2m.fields import SortedManyToManyField

from conductor.utils import get_admin_url

logger = logging.getLogger()


class Timeout(models.Model):
    name = models.CharField(max_length=16)
    UNITS_MINUTES = "minutes"
    UNITS_SECONDS = "seconds"
    UNITS_CHOICES = (
        (UNITS_MINUTES, "minutes"),
        (UNITS_SECONDS, "seconds")
    )
    timeout_units = models.CharField(max_length=16, choices=UNITS_CHOICES)
    timeout_value = models.IntegerField()

    def to_yaml(self):
        return {
            self.name: {self.timeout_units: self.timeout_value}
        }

    def __str__(self):
        return f"{self.name}: {self.timeout_value} {self.timeout_units}"

class LAVAAction(PolymorphicModel):
    namespace = models.CharField(max_length=64, null=True, blank=True)
    connection_namespace = models.CharField(max_length=64, null=True, blank=True)
    timeout = models.ForeignKey(Timeout, on_delete=models.SET_NULL, null=True)
    ACTION_DEPLOY = "deploy"
    ACTION_BOOT = "boot"
    ACTION_COMMAND = "command"
    ACTION_TEST = "test"
    ACTION_CHOICES = (
        (ACTION_DEPLOY, "deploy"),
        (ACTION_BOOT, "boot"),
        (ACTION_COMMAND, "command"),
        (ACTION_TEST, "test"),
    )
    action_type = models.CharField(max_length=16, choices=ACTION_CHOICES)

    def to_yaml(self):
        return_dict = {
            self.action_type: {}
        }
        if self.timeout:
            return_dict[self.action_type].update({
                "timeout": {self.timeout.timeout_units: self.timeout.timeout_value}
            })
        if self.namespace:
            return_dict[self.action_type].update({
                "namespace": self.namespace,
            })
        if self.connection_namespace:
            return_dict[self.action_type].update({
                "connection-namespace": self.connection_namespace
            })

        return return_dict


class TestJobMetadata(models.Model):
    name = models.CharField(max_length=32)
    metadata = models.TextField(blank=True)

    def to_yaml(self):
        return yaml.safe_load(self.metadata)

    def __str__(self):
        return self.name


class TestJobContext(models.Model):
    name = models.CharField(max_length=32)
    context = models.TextField(blank=True)

    def to_yaml(self):
        return yaml.safe_load(self.context)

    def __str__(self):
        return self.name


class TestJobTag(models.Model):
    name = models.CharField(max_length=32)

    def __str__(self):
        return self.name


class TestJob(models.Model):
    name = models.CharField(max_length=128)
    metadata = models.ForeignKey(TestJobMetadata, on_delete=models.SET_NULL, null=True, blank=True)
    context = models.ForeignKey(TestJobContext, on_delete=models.SET_NULL, null=True, blank=True)
    priority = models.IntegerField(default=50)
    VISIBILITY_PUBLIC = "public"
    VISIBILITY_GROUP = "group"
    VISIBILITY_PRIVATE = "private"
    VISIBILITY_CHOICES = (
        (VISIBILITY_PUBLIC, "public"),
        (VISIBILITY_GROUP, "group"),
        (VISIBILITY_PRIVATE, "private")
    )
    visibility = models.CharField(max_length=8, choices=VISIBILITY_CHOICES, default=VISIBILITY_PUBLIC)
    timeouts = models.ManyToManyField(Timeout)
    tags = models.ManyToManyField(TestJobTag, blank=True)
    actions = SortedManyToManyField(LAVAAction)
    is_ota_job = models.BooleanField(default=False)
    is_downgrade_job = models.BooleanField(default=False)
    is_static_delta_job = models.BooleanField(default=False)
    is_el2go_job = models.BooleanField(default=False)
    is_assemble_image_job = models.BooleanField(default=False)

    def get_job_definition(self, testplan):
        timeouts_dict = {}
        for item in self.timeouts.all():
            timeouts_dict[item.name] = {item.timeout_units: item.timeout_value}

        job_yaml = {
            "job_name": self.name,
            "visibility": self.visibility,
            "priority": self.priority,
            "timeouts": timeouts_dict,
            "actions": [action.to_yaml() for action in self.actions.all()]
        }
        if testplan:
            job_yaml.update({"device_type": testplan.lava_device_type})
        if self.metadata:
            job_yaml["metadata"] = self.metadata.to_yaml()
        if self.context:
            job_yaml["context"] = self.context.to_yaml()
        if self.tags:
            job_yaml["tags"] = list(self.tags.all().values_list('name', flat=True))
        return job_yaml

    def get_testplans(self):
        # this is used to display testplan links in the admin
        ret_string = ""
        for tp in self.testplan_set.all():
            tp_url = get_admin_url(tp)
            ret_string += f"<a href=\"{tp_url}\">{tp.id}</a> "
        return ret_string

    def __str__(self):
        return self.name


class DownloadImage(models.Model):
    name = models.CharField(max_length=32, default="image")
    url = models.CharField(max_length=256)
    compression = models.CharField(max_length=8, null=True, blank=True)
    headers = models.TextField(null=True, blank=True)
    image_arg = models.CharField(max_length=256, null=True, blank=True)

    def get_headers(self):
        return yaml.safe_load(self.headers)

    def __str__(self):
        return f"{self.name}: {self.url}"


class DeployPostprocess(models.Model):
    image = models.CharField(max_length=128)
    name = models.CharField(max_length=128)
    steps = models.TextField()

    def to_yaml(self):
        return {
            "docker": {
                "image": self.image,
                "steps": yaml.safe_load(self.steps)
            }
        }

    def __str__(self):
        return self.name


class Deployment(LAVAAction):
    # device type specific deployment
    DEPLOY_DOWNLOAD = "download"
    DEPLOY_DOWNLOADS = "downloads"
    DEPLOY_TMPFS = "tmpfs"
    DEPLOY_FLASHER = "flasher"
    DEPLOY_CHOICES = (
        (DEPLOY_DOWNLOAD, "download"),
        (DEPLOY_DOWNLOADS, "downloads"),
        (DEPLOY_TMPFS, "tmpfs"),
        (DEPLOY_FLASHER, "flasher")
    )
    deploy_to = models.CharField(max_length=16, choices=DEPLOY_CHOICES)
    images = models.ManyToManyField(DownloadImage)
    postprocess = models.ForeignKey(DeployPostprocess, blank=True, null=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=32, null=True, blank=True)

    def to_yaml(self):
        images_dict = {}
        for image in self.images.all():
            images_dict[image.name] = {"url": image.url}
            if image.compression:
                images_dict[image.name].update({"compression": image.compression})
            if image.headers:
                images_dict[image.name].update({"headers": image.get_headers()})
        deployment_dict = super().to_yaml()
        deployment_dict[self.action_type].update({
            "to": self.deploy_to,
            "images": images_dict
        })
        if self.postprocess:
            deployment_dict["deploy"].update({"postprocess": self.postprocess.to_yaml()})
        return deployment_dict

    def __str__(self):
        return f"{self.name}"


class AutoLogin(models.Model):
    login_prompt = models.CharField(max_length=32)
    password_prompt = models.CharField(max_length=32)
    username = models.CharField(max_length=32)
    password = models.CharField(max_length=32)
    login_commands = models.TextField(null=True, blank=True)
    name = models.CharField(max_length=32)

    def to_yaml(self):
        auto_login_dict = {
            "login_prompt": self.login_prompt,
            "username": self.username,
            "password_prompt": self.password_prompt,
            "password": self.password,
            "login_commands": yaml.safe_load(self.login_commands)
        }
        return auto_login_dict

    def __str__(self):
        return f"{self.name}"


class Boot(LAVAAction):
    # job specific boot action
    prompts = models.TextField(null=True, blank=True)
    METHOD_MINIMAL = "minimal"
    METHOD_CHOICES = (
        (METHOD_MINIMAL, "minimal"),
    )
    method = models.CharField(max_length=32, choices=METHOD_CHOICES)
    transfer_overlay = models.BooleanField(default=True)
    transfer_overlay_download = models.CharField(max_length=512, null=True, blank=True)
    transfer_overlay_unpack = models.CharField(max_length=512, null=True, blank=True)
    auto_login = models.ForeignKey(AutoLogin, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=32, null=True, blank=True)  # make not null!!

    def to_yaml(self):
        boot_dict = super().to_yaml()
        boot_dict[self.action_type].update({
            "method" : self.method,
        })
        if self.prompts:
            boot_dict[self.action_type].update({"prompts": yaml.safe_load(self.prompts)})
        if self.auto_login:
            boot_dict[self.action_type].update({"auto_login": self.auto_login.to_yaml()})
        if self.transfer_overlay:
            # assume overaly fields are not empty
            # ToDo: check this on object creation
            boot_dict[self.action_type].update(
                {"transfer_overlay": {
                    "download_command": self.transfer_overlay_download,
                    "unpack_command": self.transfer_overlay_unpack
                }
            })
        return boot_dict

    def __str__(self):
        return f"{self.name}"


class InteractiveCommand(models.Model):
    command = models.CharField(max_length=256)
    name = models.CharField(max_length=32)
    wait_for_prompt = models.BooleanField(default=False)
    success_messages = models.TextField()

    def to_yaml(self):
        return {
            "command": self.command,
            "name": self.name,
            "wait_for_prompt": self.wait_for_prompt,
            "successes": yaml.safe_load(self.success_messages)
        }

    def __str__(self):
        return self.name


class TestDefinition(models.Model):
    TYPE_GIT = "git"
    TYPE_INTERACTIVE = "interactive"
    TYPE_CHOICES = [
        (TYPE_GIT, "git"),
        (TYPE_INTERACTIVE, "interactive")
    ]
    testtype = models.CharField(
        max_length=16,
        choices=TYPE_CHOICES,
        default=TYPE_GIT
    )
    name = models.CharField(max_length=128)
    # intended to allow filtering and
    # allow different parameters for different devices
    # empty means it applies to all devices
    device_type = models.CharField(max_length=32, null=True, blank=True)
    path = models.CharField(max_length=256, null=True, blank=True)
    repository = models.CharField(max_length=256, null=True, blank=True)
    branch = models.CharField(max_length=64, null=True, blank=True)
    parameters = models.TextField(blank=True)
    prompts = models.TextField(default="[]")
    interactive_commands = SortedManyToManyField(InteractiveCommand, blank=True)

    def parameters_yaml(self, substitutions=None):
        params = self.parameters
        if substitutions:
            # replace items in params
            pass
        return yaml.safe_load(params)

    def to_yaml(self, substitutions=None):
        td_dict = {}
        if self.testtype == TestDefinition.TYPE_GIT:
            td_dict = {
                "repository": self.repository,
                "from": self.testtype,
                "path": self.path,
                "name": self.name
            }
            if self.branch:
                td_dict.update({"branch": self.branch})
            if self.parameters:
                td_dict.update({"parameters": self.parameters_yaml()})
        if self.testtype == TestDefinition.TYPE_INTERACTIVE:
            td_dict = {
                "name": self.name,
                "prompts": yaml.safe_load(self.prompts),
                "script": []
            }
            for command in self.interactive_commands.all():
                td_dict["script"].append(command.to_yaml())
        return td_dict

    def __str__(self):
        return f"{self.name} ({self.testtype}) ({self.device_type})"


class TestAction(LAVAAction):
    name = models.CharField(max_length=64)
    definitions = SortedManyToManyField(TestDefinition)

    def to_yaml(self):
        return_dict = super().to_yaml()
        if self.definitions.filter(testtype=TestDefinition.TYPE_GIT):
            return_dict[self.action_type].update({"definitions": []})
        if self.definitions.filter(testtype=TestDefinition.TYPE_INTERACTIVE):
            return_dict[self.action_type].update({"interactive": []})
        for definition in self.definitions.filter(testtype=TestDefinition.TYPE_GIT):
            return_dict[self.action_type]["definitions"].append(definition.to_yaml())
        for definition in self.definitions.filter(testtype=TestDefinition.TYPE_INTERACTIVE):
            return_dict[self.action_type]["interactive"].append(definition.to_yaml())
        return return_dict


    def __str__(self):
        return f"{self.name}"


class CommandAction(LAVAAction):
    name = models.CharField(max_length=32)

    def to_yaml(self):
        command_dict = {
            "command": {"name": self.name}
        }
        if self.namespace:
            command_dict["command"].update({"namespace": self.namespace})
        if self.connection_namespace:
            command_dict["command"].update({"connection-namespace": self.connection_namespace})
        return command_dict

    def __str__(self):
        return f"{self.name} ({self.namespace})"


class TestPlan(models.Model):
    name = models.CharField(max_length=64)
    testjobs = SortedManyToManyField(TestJob)
    lava_device_type = models.CharField(max_length=32)

    def __str__(self):
        return self.name
