# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

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
        '-B',
        '--queues=' + ','.join(queues),
        '--max-tasks-per-child=5000',
        '--max-memory-per-child=1500000',
        '--loglevel=DEBUG'
    ] + sys.argv[1:]
    os.execvp(sys.executable, argv)


if __name__ == "__main__":
    main()
