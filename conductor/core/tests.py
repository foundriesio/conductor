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

from django.test import TestCase
from unittest.mock import patch
from unittest.mock import MagicMock

from .models import Project


# model tests

class ProjectTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="testProject1",
            secret="webhooksecret",
            lava_url="http://lava.example.com/api/v0.2/",
            lava_api_token="lavatoken",
        )

    @patch('requests.post')
    def test_submit_lava_job(self, post_mock):
        definition = "lava test definition"
        response_mock = MagicMock()
        response_mock.status_code = 201
        response_mock.json.return_value = {'job_ids': ['123']}
        post_mock.return_value = response_mock

        ret_list = self.project.submit_lava_job(definition)
        post_mock.assert_called()
        self.assertEqual(ret_list, ['123'])
