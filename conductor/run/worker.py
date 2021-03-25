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

from conductor.settings import CELERY_TASK_DEFAULT_QUEUE
import os
import sys

def main():
    queues = set()
    queues.add(CELERY_TASK_DEFAULT_QUEUE)
    argv = [
        sys.executable, '-m', 'celery',
        # default celery args:
        '-A', 'conductor',
        'worker',
        '--queues=' + ','.join(queues),
        '--max-tasks-per-child=5000',
        '--max-memory-per-child=1500000',
        '--loglevel=INFO'
    ] + sys.argv[1:]
    os.execvp(sys.executable, argv)


if __name__ == "__main__":
    main()
