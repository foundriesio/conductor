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

from django.test import TestCase, Client
from conductor.core.models import Project, LAVABackend, LAVADeviceType, LAVADevice
from conductor.celery import app as celeryapp
from unittest.mock import MagicMock, patch


class ApiViewTest(TestCase):
    def setUp(self):
        self.lavabackend1 = LAVABackend.objects.create(
            name="testLavaBackend1",
            lava_url="http://lava.example.com/api/v0.2/",
            lava_api_token="lavatoken",
        )
        self.project_secret = "webhooksecret"
        self.project = Project.objects.create(
            name="testProject1",
            secret=self.project_secret,
            lava_backend=self.lavabackend1
        )
        self.device_type = LAVADeviceType.objects.create(
            name="name1",
            net_interface="eth0",
            project=self.project
        )
        self.device = LAVADevice.objects.create(
            device_type=self.device_type,
            name="device1",
            auto_register_name="device_auto_reg_1",
            project=self.project
        )
        self.client = Client()

    @patch("conductor.core.tasks.update_build_commit_id.delay", return_value="git_sha_1")
    @patch("conductor.core.models.Project.submit_lava_job", return_value=[123])
    @patch("conductor.core.tasks._get_os_tree_hash", return_value="ostreehash")
    def test_jobserv_webhook(self, requests_mock, submit_lava_job_mock, update_commit_mock):
        request_body_dict = {
            "status": "PASSED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/testProject1/lmp/builds/73/",
            "trigger_name": "platform-master",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"Token: {self.project_secret}"}
        )
        self.assertEqual(response.status_code, 201)
        # check if build was created
        build = self.project.build_set.first()
        self.assertIsNotNone(build)
        self.assertEqual(build.build_id, 1)
        self.assertEqual(build.run_set.all().count(), 1)
        requests_mock.assert_called()
        update_commit_mock.assert_called()

    def test_jobserv_webhook_incorrect_header(self):
        request_body_dict = {
            "status": "PASSED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/testProject1/lmp/builds/73/",
            "trigger_name": "platform-master",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig": "Token: foo"}
        )
        self.assertEqual(response.status_code, 403)

    def test_jobserv_webhook_missing_header(self):
        request_body_dict = {
            "status": "PASSED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/testProject1/lmp/builds/73/",
            "trigger_name": "platform-master",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_jobserv_webhook_container_build(self):
        request_body_dict = {
            "status": "PASSED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/testProject1/lmp/builds/73/",
            "trigger_name": "containers-master",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"Token: {self.project_secret}"}
        )
        self.assertEqual(response.status_code, 200)

    def test_jobserv_webhook_wrong_project(self):
        request_body_dict = {
            "status": "PASSED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/testprojectdoesnotexist/lmp/builds/73/",
            "trigger_name": "platform-master",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"Token: {self.project_secret}"}
        )
        self.assertEqual(response.status_code, 404)

    def test_jobserv_webhook_malformed_json(self):
        response = self.client.post(
            "/api/jobserv/",
            "wrong request body:",
            content_type="application/json",
            **{"HTTP_X_Jobserv_Sig":"Token: "}
        )
        self.assertEqual(response.status_code, 400)

    def test_jobserv_webhook_missing_id(self):
        request_body_dict = {
            "status": "PASSED",
            "url": "https://api.foundries.io/projects/testProject1/lmp/builds/73/",
            "trigger_name": "platform-master",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"Token: {self.project_secret}"}
        )
        self.assertEqual(response.status_code, 400)

    def test_jobserv_webhook_missing_url(self):
        request_body_dict = {
            "status": "PASSED",
            "build_id": 1,
            "trigger_name": "platform-master",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"Token: {self.project_secret}"}
        )
        self.assertEqual(response.status_code, 400)

    def test_jobserv_webhook_get(self):
        response = self.client.get(
            "/api/jobserv/",
            **{"HTTP_X_JobServ_Sig":f"Token: {self.project_secret}"}
        )
        self.assertEqual(response.status_code, 405)

    @patch("conductor.core.tasks.merge_lmp_manifest.delay")
    def test_jobserv_lmp_webhook(self, merge_lmp_manifest_mock):
        request_body_dict = {
            "status": "PASSED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/testProject1/lmp/builds/73/",
            "trigger_name": "platform-master",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        response = self.client.post(
            "/api/lmp/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"Token: {self.project_secret}"}
        )
        self.assertEqual(response.status_code, 200)
        # check if build was created
        merge_lmp_manifest_mock.assert_called()

    def test_jobserv_lmp_get(self):
        response = self.client.get(
            "/api/lmp/",
            **{"HTTP_X_JobServ_Sig":f"Token: {self.project_secret}"}
        )
        self.assertEqual(response.status_code, 405)

    @patch("conductor.core.tasks.check_device_ota_completed.delay")
    def test_device_webhook(self, check_device_ota_completed_mock):
        request_body_dict = {
            "name": self.device.auto_register_name,
            "project": self.project.name,
        }
        response = self.client.post(
            "/api/device/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_DeviceOta_Sig":f"Token: {self.project_secret}"}
        )
        self.assertEqual(response.status_code, 200)
        check_device_ota_completed_mock.assert_called()

    @patch("conductor.core.tasks.check_device_ota_completed.delay")
    def test_device_webhook_wrong_token(self, check_device_ota_completed_mock):
        request_body_dict = {
            "name": self.device.auto_register_name,
            "project": self.project.name,
        }
        response = self.client.post(
            "/api/device/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_DeviceOta_Sig":"Token: foo"}
        )
        self.assertEqual(response.status_code, 403)
        check_device_ota_completed_mock.assert_not_called()

    @patch("conductor.core.tasks.check_device_ota_completed.delay")
    def test_device_webhook_missing_token(self, check_device_ota_completed_mock):
        request_body_dict = {
            "name": self.device.auto_register_name,
            "project": self.project.name,
        }
        response = self.client.post(
            "/api/device/",
            request_body_dict,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        check_device_ota_completed_mock.assert_not_called()

    @patch("conductor.core.tasks.check_device_ota_completed.delay")
    def test_device_webhook_wrong_project(self, check_device_ota_completed_mock):
        request_body_dict = {
            "name": self.device.auto_register_name,
            "project": "foo",
        }
        response = self.client.post(
            "/api/device/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_DeviceOta_Sig":f"Token: {self.project_secret}"}
        )
        self.assertEqual(response.status_code, 404)
        check_device_ota_completed_mock.assert_not_called()

    @patch("conductor.core.tasks.check_device_ota_completed.delay")
    def test_device_webhook_missing_device(self, check_device_ota_completed_mock):
        request_body_dict = {
            "name": "foo",
            "project": self.project.name,
        }
        response = self.client.post(
            "/api/device/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_DeviceOta_Sig":f"Token: {self.project_secret}"}
        )
        self.assertEqual(response.status_code, 404)
        check_device_ota_completed_mock.assert_not_called()
