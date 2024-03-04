#!/usr/bin/env python

# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

import os
import sys


def main():
    """Run administrative tasks."""
    testing = False
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "test.settings")

    else:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'conductor.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
