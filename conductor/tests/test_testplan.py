# Copyright 2022 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

from django.conf import settings
from django.test import TestCase
from unittest.mock import patch, MagicMock, PropertyMock

from conductor.testplan.models import (
    Timeout,
    LAVAAction,
    TestJobMetadata,
    TestJobContext,
    TestJob,
    DownloadImage,
    DeployPostprocess,
    Deployment,
    AutoLogin,
    Boot,
    InteractiveCommand,
    TestDefinition,
    TestAction,
    CommandAction,
    TestPlan,
)


class TimeoutTest(TestCase):
    def setUp(self):
        self.timeout1 = Timeout.objects.create(
            name="timeout1",
            timeout_units=Timeout.UNITS_MINUTES,
            timeout_value=1
        )

    def test_to_yaml(self):
        reference_dict = {
            "timeout1": {Timeout.UNITS_MINUTES: 1}
        }
        self.assertEqual(self.timeout1.to_yaml(), reference_dict)


class TestJobMetadataTest(TestCase):
    def setUp(self):
        self.metadata1 = TestJobMetadata(
            name = "metadata1",
            metadata = "key1: value1"
        )

    def test_to_yaml(self):
        reference_dict = {
            "key1": "value1"
        }
        self.assertEqual(self.metadata1.to_yaml(), reference_dict)


class TestJobContextTest(TestCase):
    def setUp(self):
        self.context1 = TestJobContext(
            name = "context1",
            context = "key1: value1"
        )

    def test_to_yaml(self):
        reference_dict = {
            "key1": "value1"
        }
        self.assertEqual(self.context1.to_yaml(), reference_dict)


class DeployPostprocessTest(TestCase):
    def setUp(self):
        self.deploy1 = DeployPostprocess(
            name = "deploy1",
            image = "image_url",
            steps = "- step1\n- step2"
        )

    def test_to_yaml(self):
        reference_dict = {
            "docker": {
                "image": "image_url",
                "steps": ["step1", "step2"]
            }
        }
        self.assertEqual(self.deploy1.to_yaml(), reference_dict)


class DeploymentTest(TestCase):
    def setUp(self):
        self.downloadImage1 = DownloadImage(
            name="downloadimage1",
            url="https://example.com/image1",
            compression="gz",
            headers="HEADER1: VALUE1"
        )
        self.downloadImage1.save()
        self.downloadImage2 = DownloadImage(
            name="downloadimage2",
            url="https://example.com/image2",
            compression="gz",
            headers="HEADER1: VALUE1"
        )
        self.downloadImage2.save()
        self.deployPostprocess1 = DeployPostprocess(
            name = "deploypostprocess1",
            image = "image_url",
            steps = "- step1\n- step2"
        )
        self.deployPostprocess1.save()
        self.deployment1 = Deployment(
            deploy_to=Deployment.DEPLOY_DOWNLOADS,
            name="deploy1",
            postprocess=self.deployPostprocess1,
            action_type="deploy"
        )
        self.deployment1.save()
        self.deployment1.images.add(self.downloadImage1)
        self.deployment1.images.add(self.downloadImage2)
        self.deployment2 = Deployment(
            deploy_to=Deployment.DEPLOY_FLASHER,
            name="deploy2",
            action_type="deploy",
            failure_retry=3
        )
        self.deployment2.save()
        self.deployment2.images.add(self.downloadImage1)
        self.deployment2.images.add(self.downloadImage2)

    def test_to_yaml(self):
        reference_dict = {
            "deploy": {
                "to": "downloads",
                "images": {
                    "downloadimage1": {
                        "url": "https://example.com/image1",
                        "compression": "gz",
                        "headers": {
                            "HEADER1": "VALUE1"
                        }
                    },
                    "downloadimage2": {
                        "url": "https://example.com/image2",
                        "compression": "gz",
                        "headers": {
                            "HEADER1": "VALUE1"
                        }
                    }
                },
                "postprocess": {
                    "docker": {
                        "image": "image_url",
                        "steps": ["step1", "step2"]
                    }
                },
            }
        }
        self.assertEqual(self.deployment1.to_yaml(), reference_dict)
    def test_retry_yaml(self):
        reference_dict = {
            "deploy": {
                "to": "flasher",
                "failure_retry": 3,
                "images": {
                    "downloadimage1": {
                        "url": "https://example.com/image1",
                        "compression": "gz",
                        "headers": {
                            "HEADER1": "VALUE1"
                        }
                    },
                    "downloadimage2": {
                        "url": "https://example.com/image2",
                        "compression": "gz",
                        "headers": {
                            "HEADER1": "VALUE1"
                        }
                    }
                }
            }
        }
        self.assertEqual(self.deployment2.to_yaml(), reference_dict)

        #ToDo: cover more deployment options

class AutoLoginTest(TestCase):
    def setUp(self):
        self.autoLogin1 = AutoLogin(
            login_prompt="login:",
            password_prompt="Password",
            username="user",
            password="secret",
            login_commands="- sudo su\n- secret",
            name="autologin1"
        )

    def test_to_yaml(self):
        reference_dict = {
            "login_prompt": "login:",
            "username": "user",
            "password_prompt": "Password",
            "password": "secret",
            "login_commands": ["sudo su", "secret"]
        }
        self.assertEqual(self.autoLogin1.to_yaml(), reference_dict)


class BootTest(TestCase):
    def setUp(self):
        self.maxDiff = None
        self.autoLogin1 = AutoLogin(
            login_prompt="login:",
            password_prompt="Password",
            username="user",
            password="secret",
            login_commands="- sudo su\n- secret",
            name="autologin1",
        )
        self.boot1 = Boot(
            name="boot1",
            method=Boot.METHOD_MINIMAL,
            transfer_overlay=True,
            transfer_overlay_download="cd /home ; wget",
            transfer_overlay_unpack="tar -C /home/fio -xzf",
            auto_login=self.autoLogin1,
            prompts="- \"Password:\"\n- root@imx8mmevk",
            action_type="boot"
        )

    def test_to_yaml(self):
        reference_dict = {
            "boot": {
                "prompts": ["Password:", "root@imx8mmevk"],
                "method": "minimal",
                "auto_login": {
                    "login_prompt": "login:",
                    "username": "user",
                    "password_prompt": "Password",
                    "password": "secret",
                    "login_commands": ["sudo su", "secret"]
                },
                "transfer_overlay": {
                    "download_command": "cd /home ; wget",
                    "unpack_command": "tar -C /home/fio -xzf"
                }
            }
        }
        self.assertEqual(self.boot1.to_yaml(), reference_dict)


class TestDefinitionTests(TestCase):
    def setUp(self):
        self.testDefinition1 = TestDefinition(
            testtype=TestDefinition.TYPE_GIT,
            name="definition1",
            device_type="dev_type1",
            path="example/path",
            repository="https://example.com/git"
        )

    def test_to_yaml(self):
        reference_dict = {
            "repository": "https://example.com/git",
            "from": "git",
            "path": "example/path",
            "name": "definition1"
        }
        self.assertEqual(self.testDefinition1.to_yaml(), reference_dict)

    # ToDo: cover more cases: interactive, parameters


class TestActionTests(TestCase):
    def setUp(self):
        self.testDefinition1 = TestDefinition(
            testtype=TestDefinition.TYPE_GIT,
            name="definition1",
            device_type="dev_type1",
            path="example/path",
            repository="https://example.com/git",
        )
        self.testDefinition1.save()
        self.testDefinition2 = TestDefinition(
            testtype=TestDefinition.TYPE_GIT,
            name="definition2",
            device_type="dev_type1",
            path="example/path2",
            repository="https://example.com/git"
        )
        self.testDefinition2.save()
        self.timeout1 = Timeout(
            name="timeout1",
            timeout_units=Timeout.UNITS_MINUTES,
            timeout_value=1
        )
        self.timeout1.save()
        self.testAction1 = TestAction(
            name="testaction1",
            timeout=self.timeout1,
            action_type="test"
        )
        self.testAction1.save()
        self.testAction1.definitions.add(self.testDefinition1)
        self.testAction1.definitions.add(self.testDefinition2)
        self.testAction1.save()

    def test_to_yaml(self):
        reference_dict = {
            "test": {
                "definitions": 
                    [{"from": "git",
                      "name": "definition1",
                      "path": "example/path",
                      "repository": "https://example.com/git"},
                     {"from": "git",
                      "name": "definition2",
                      "path": "example/path2",
                      "repository": "https://example.com/git"}],
                "timeout": {"minutes": 1}
            }
        }

        self.assertEqual(self.testAction1.to_yaml(), reference_dict)
