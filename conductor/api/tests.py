# Copyright 2021-2024 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

import hashlib
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
        self.project_parent = Project.objects.create(
            name="parentProject",
            secret=self.project_secret,
            lava_backend=self.lavabackend1,
            fio_lmp_manifest_url="https://github.com/example/repository"
        )
        self.project_partner = Project.objects.create(
            name="testProjectPartner1",
            secret=self.project_secret,
            lava_backend=self.lavabackend1,
            fio_lmp_manifest_url="https://github.com/example/repository",
            forked_from="parentProject",
            fio_lmp_manifest_branch="main"
        )
        self.device_type = LAVADeviceType.objects.create(
            name="name1",
            architecture="aarch64",
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

    @patch("conductor.core.tasks.tag_build_runs.si")
    @patch("conductor.core.tasks.create_build_run.si")
    @patch("conductor.core.tasks.update_build_commit_id.si")
    def test_jobserv_webhook(self, ubci_mock, cbr_mock, tag_mock):
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
        tag_mock.assert_called()

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

    @patch("conductor.core.tasks.tag_build_runs.si")
    @patch("conductor.core.tasks.create_build_run.si")
    @patch("conductor.core.tasks.update_build_commit_id.si")
    def test_jobserv_webhook_container_build(self, build_commit_mock, build_run_mock, tag_mock):
        request_body_dict = {
            "status": "PASSED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/testProject1/lmp/builds/73/",
            "trigger_name": "containers-master",
            "runs": [
                {"url": "https://example.com", "name": "build-aarch64"}
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
        build_run_mock.assert_called()
        build_commit_mock.assert_called()
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

    # api/lmp

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

    # api/partner

    @patch("conductor.core.tasks.merge_project_lmp_manifest.delay")
    def test_partner_webhook(self, merge_project_manifest_mock):
        request_body_dict = {
            "status": "PASSED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/parentProject/lmp/builds/73/",
            "trigger_name": "platform-main",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project_partner.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/partner/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"sha256: {sig.hexdigest()}"}
        )
        apicallback = APICallback.objects.first()
        self.assertEqual(request_body_dict, json.loads(apicallback.content))
        self.assertEqual(response.status_code, 201)
        # check if build was created
        merge_project_manifest_mock.assert_called_with(self.project_partner.id)

    @patch("conductor.core.tasks.merge_project_lmp_manifest.delay")
    def test_jobserv_lmp_webhook_failed(self, merge_project_manifest_mock):
        request_body_dict = {
            "status": "FAILED",
            "build_id": 1,
            "url": "https://api.foundries.io/projects/parentProject/lmp/builds/73/",
            "trigger_name": "platform-main",
            "runs": [
                {"url": "example.com", "name": "name1"}
            ]
        }
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project_partner.secret.encode(), msg=data.encode(), digestmod="sha256")
        response = self.client.post(
            "/api/partner/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_JobServ_Sig":f"sha256: {sig.hexdigest()}"}
        )
        apicallback = APICallback.objects.first()
        self.assertEqual(request_body_dict, json.loads(apicallback.content))
        self.assertEqual(response.status_code, 200)
        # check if build was created
        merge_project_manifest_mock.assert_not_called()

    def test_partner_get(self):
        response = self.client.get(
            "/api/partner/",
            **{"HTTP_X_JobServ_Sig":f"Token: {self.project_secret}"}
        )
        self.assertEqual(response.status_code, 405)

    # api/device

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

    @patch("conductor.core.tasks.merge_project_lmp_manifest.delay")
    def test_process_github_webhook(self, merge_project_lmp_manifest_mock):
        request_body_dict = {
            "action": "opened",
            "issue": {
                "url": "https://api.github.com/repos/octocat/Hello-World/issues/1347",
                "number": 1347,
            },
            "repository" : {
                "id": 1296269,
                "full_name": "example/repository",
                "owner": {
                    "login": "octocat",
                    "id": 1,
                },
            },
            "sender": {
                "login": "octocat",
                "id": 1,
            }
        }
        data = json.dumps(request_body_dict, cls=ISO8601_JSONEncoder)
        sig = hmac.new(self.project.secret.encode(), msg=data.encode(), digestmod=hashlib.sha256)
        print(sig.hexdigest())

        response = self.client.post(
            "/api/github/",
            request_body_dict,
            content_type="application/json",
            **{"HTTP_X_Hub_Signature_256":f"sha256={sig.hexdigest()}"}
        )
        apicallback = APICallback.objects.first()
        self.assertEqual(request_body_dict, json.loads(apicallback.content))
        self.assertEqual(response.status_code, 200)
        # check if merge was attempted
        merge_project_lmp_manifest_mock.assert_called_with(self.project_partner.id)
