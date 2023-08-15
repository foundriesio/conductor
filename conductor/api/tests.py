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

import hmac
import json
from django.test import TestCase, Client
from django.conf import settings
from conductor.api.models import APICallback
from conductor.core.models import Project, LAVABackend, LAVADeviceType, LAVADevice, Build, Run
from conductor.core.utils import ISO8601_JSONEncoder
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
        self.build = Build.objects.create(
            url="https://example.com/",
            build_id=123,
            project=self.project,
            commit_id="abcdef123456",
            is_release=False,
            tag="master",
            build_reason="test build #1"
        )
        self.run = Run.objects.create(
            build=self.build,
            device_type=self.device_type.name,
            ostree_hash="123456abcdef",
            run_name=self.device_type.name
        )
        self.client = Client()

    @patch("conductor.core.tasks.create_build_run.si")
    @patch("conductor.core.tasks.update_build_commit_id.si")
    def test_jobserv_webhook(self, ubci_mock, cbr_mock):
        request_body_dict = {
            "status": "PASSED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/testProject1/lmp/builds/73/",
            "trigger_name": "platform-master",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"sha256: {sig.hexdigest()}"}
        )
        self.assertEqual(response.status_code, 201)
        # check if build was created
        build = self.project.build_set.last()
        apicallback = APICallback.objects.first()
        self.assertEqual(request_body_dict, json.loads(apicallback.content))
        self.assertIsNotNone(build)
        self.assertEqual(build.build_id, 1)
        cbr_mock.assert_called()
        ubci_mock.assert_called()

    @patch("conductor.core.tasks._get_ci_url", return_value="abc")
    @patch("conductor.core.tasks.restart_ci_run")
    @patch("conductor.core.tasks.create_build_run.si")
    @patch("conductor.core.tasks.update_build_commit_id.si")
    def test_jobserv_webhook_failed(self, ubci_mock, cbr_mock, restart_mock, get_mock):
        request_body_dict = {
            "status": "FAILED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/testProject1/lmp/builds/73/",
            "trigger_name": "platform-master",
            "runs": [
                {"url": "http://example.com/name2/", "log_url": "http://example.com/name2/log", "name": "name2", "status": "PASSED"},
                {"url": "http://example.com/name1/", "log_url": "http://example.com/name1/log", "name": "name1", "status": "FAILED"}
            ]
        }
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"sha256: {sig.hexdigest()}"}
        )
        self.assertEqual(response.status_code, 200)
        # check if build was created
        build = self.project.build_set.last()
        apicallback = APICallback.objects.first()
        self.assertEqual(request_body_dict, json.loads(apicallback.content))
        self.assertIsNotNone(build)
        self.assertEqual(build.build_id, 1)
        cbr_mock.assert_not_called()
        ubci_mock.assert_not_called()
        restart_mock.assert_called_with(build.project, "http://example.com/name1/")
        build.refresh_from_db()
        self.assertEqual(build.restart_counter, 1)

    @patch("conductor.core.tasks._get_ci_url", return_value="abc")
    @patch("conductor.core.tasks.restart_ci_run")
    @patch("conductor.core.tasks.create_build_run.si")
    @patch("conductor.core.tasks.update_build_commit_id.si")
    def test_jobserv_webhook_failed_3times(self, ubci_mock, cbr_mock, restart_mock, get_mock):
        request_body_dict = {
            "status": "FAILED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/testProject1/lmp/builds/73/",
            "trigger_name": "platform-master",
            "runs": [
                {"url": "http://example.com/name2/", "log_url": "http://example.com/name2/log", "name": "name2", "status": "PASSED"},
                {"url": "http://example.com/name1/", "log_url": "http://example.com/name1/log", "name": "name1", "status": "FAILED"}
            ]
        }
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"sha256: {sig.hexdigest()}"}
        )
        self.assertEqual(response.status_code, 200)
        # check if build was created
        build = self.project.build_set.last()
        apicallback = APICallback.objects.first()
        self.assertEqual(request_body_dict, json.loads(apicallback.content))
        self.assertIsNotNone(build)
        self.assertEqual(build.build_id, 1)
        cbr_mock.assert_not_called()
        ubci_mock.assert_not_called()
        restart_mock.assert_called_with(build.project, "http://example.com/name1/")
        build.refresh_from_db()
        self.assertEqual(build.restart_counter, 1)
        build.restart_counter = settings.MAX_BUILD_RESTARTS
        build.save()
        restart_mock.reset_mock()
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"sha256: {sig.hexdigest()}"}
        )
        self.assertEqual(response.status_code, 200)
        restart_mock.assert_not_called()

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
            **{"HTTP_X_JobServ_Sig": "sha256: foo"}
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

    @patch("conductor.core.tasks.tag_build_runs.delay")
    def test_jobserv_webhook_container_build(self, tag_mock):
        request_body_dict = {
            "status": "PASSED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/testProject1/lmp/builds/73/",
            "trigger_name": "containers-master",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"sha256: {sig.hexdigest()}"}
        )
        apicallback = APICallback.objects.first()
        self.assertEqual(request_body_dict, json.loads(apicallback.content))
        self.assertEqual(response.status_code, 201)
        tag_mock.assert_called()

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
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"sha256: {sig.hexdigest()}"}
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
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"sha256: {sig.hexdigest()}"}
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
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/jobserv/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"sha256: {sig.hexdigest()}"}
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
            "trigger_name": "build-release",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/lmp/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"sha256: {sig.hexdigest()}"}
        )
        apicallback = APICallback.objects.first()
        self.assertEqual(request_body_dict, json.loads(apicallback.content))
        self.assertEqual(response.status_code, 201)
        # check if build was created
        merge_lmp_manifest_mock.assert_called()

    @patch("conductor.core.tasks.merge_lmp_manifest.delay")
    def test_jobserv_lmp_webhook_stable(self, merge_lmp_manifest_mock):
        request_body_dict = {
            "status": "PASSED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/testProject1/lmp/builds/73/",
            "trigger_name": "build-release-stable",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/lmp/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"sha256: {sig.hexdigest()}"}
        )
        apicallback = APICallback.objects.first()
        self.assertEqual(request_body_dict, json.loads(apicallback.content))
        self.assertEqual(response.status_code, 201)
        # check if build was created
        merge_lmp_manifest_mock.assert_called()
    @patch("conductor.core.tasks.merge_lmp_manifest.delay")
    def test_jobserv_lmp_webhook_failed(self, merge_lmp_manifest_mock):
        request_body_dict = {
            "status": "FAILED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/testProject1/lmp/builds/73/",
            "trigger_name": "build-release",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/lmp/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"sha256: {sig.hexdigest()}"}
        )
        apicallback = APICallback.objects.first()
        self.assertEqual(request_body_dict, json.loads(apicallback.content))
        self.assertEqual(response.status_code, 200)
        # check if build was created
        merge_lmp_manifest_mock.assert_not_called()

    @patch("conductor.core.tasks.schedule_lmp_pr_tests.delay")
    @patch("conductor.core.tasks.merge_lmp_manifest.delay")
    def test_jobserv_lmp_webhook_wrong_target(self, merge_lmp_manifest_mock, lmp_pr_tests_mock):
        request_body_dict = {
            "status": "PASSED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/testProject1/lmp/builds/73/",
            "trigger_name": "Code Review",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/lmp/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"sha256: {sig.hexdigest()}"}
        )
        self.assertEqual(response.status_code, 201)
        # check if build was created
        merge_lmp_manifest_mock.assert_not_called()
        lmp_pr_tests_mock.assert_called()

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
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/device/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_DeviceOta_Sig":f"sha256: {sig.hexdigest()}"}
        )
        apicallback = APICallback.objects.first()
        self.assertEqual(request_body_dict, json.loads(apicallback.content))
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
            **{"HTTP_X_DeviceOta_Sig":f"Token: {self.project_secret}"}
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
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/device/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_DeviceOta_Sig":f"sha256: {sig.hexdigest()}"}
        )
        self.assertEqual(response.status_code, 404)
        check_device_ota_completed_mock.assert_not_called()

    @patch("conductor.core.tasks.check_device_ota_completed.delay")
    def test_device_webhook_missing_device(self, check_device_ota_completed_mock):
        request_body_dict = {
            "name": "foo",
            "project": self.project.name,
        }
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/device/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_DeviceOta_Sig":f"sha256: {sig.hexdigest()}"}
        )
        self.assertEqual(response.status_code, 404)
        check_device_ota_completed_mock.assert_not_called()

    def test_fiotest_context(self):
        response = self.client.get(
            f"/api/context/{self.project.name}/{self.build.build_id}/{self.device_type.name}/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["INTERFACE"], self.device_type.net_interface)
        self.assertEqual(response.json()["TARGET"], f"{self.build.build_id}")
        self.assertEqual(response.json()["OSTREE_HASH"], self.run.ostree_hash)

    def test_fiotest_context_bad_project(self):
        response = self.client.get(
            f"/api/context/foo/{self.build.build_id}/{self.device_type.name}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_fiotest_context_bad_build(self):
        response = self.client.get(
            f"/api/context/{self.project.name}/111/{self.device_type.name}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_fiotest_context_bad_device(self):
        response = self.client.get(
            f"/api/context/{self.project.name}/{self.build.build_id}/foo/"
        )
        self.assertEqual(response.status_code, 404)
