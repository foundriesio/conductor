# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

import os
import sys


def main():
    argv = [
        sys.executable, '-m', 'conductor.manage', 'lava_listener'
    ] + sys.argv[1:]
    os.execvp(sys.executable, argv)


if __name__ == "__main__":
    main()
