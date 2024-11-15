#!/bin/bash

# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

REPOSITORY_DIR=""
REPOSITORY_REMOTE=origin
REPOSITORY_DEFAULT_BRANCH=master

usage() {
    echo "Usage: $0 [-d <repository_dir>] [-r <repository_remote>]
                    [-b <repository default branch name>]
                    " 1>&2
    exit 1
}

while getopts "d:r:b:" o; do
  case "$o" in
    # The current working directory will be used by default.
    # Use '-p' specify partition that used for fio test.
    d) REPOSITORY_DIR="${OPTARG}" ;;
    r) REPOSITORY_REMOTE="${OPTARG}" ;;
    b) REPOSITORY_DEFAULT_BRANCH="${OPTARG}";;
    *) usage ;;
  esac
done

cd "${REPOSITORY_DIR}"
git fetch --all --tags
git checkout "${REPOSITORY_DEFAULT_BRANCH}"
git reset --hard "${REPOSITORY_REMOTE}/${REPOSITORY_DEFAULT_BRANCH}"
