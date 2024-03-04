#!/bin/bash

# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

REPOSITORY_DIR=""
REPOSITORY_REMOTE=origin
COMMIT_MESSAGE="Force container rebuild"
REPOSITORY_DEFAULT_BRANCH=master
CONTAINERS_FILE=""

usage() {
    echo "Usage: $0 [-d <repository_dir>] [-r <repository_remote>]
                    [-m <commit message>] [-b <repository default branch name>]" 1>&2
    exit 1
}

while getopts "d:r:m:b:f:" o; do
  case "$o" in
    # The current working directory will be used by default.
    # Use '-p' specify partition that used for fio test.
    d) REPOSITORY_DIR="${OPTARG}" ;;
    r) REPOSITORY_REMOTE="${OPTARG}" ;;
    m) COMMIT_MESSAGE="${OPTARG}" ;;
    b) REPOSITORY_DEFAULT_BRANCH="${OPTARG}";;
    f) CONTAINERS_FILE="${OPTARG}";;
    *) usage ;;
  esac
done

cd "${REPOSITORY_DIR}"
git checkout "${REPOSITORY_DEFAULT_BRANCH}"
git pull "${REPOSITORY_REMOTE}" "${REPOSITORY_DEFAULT_BRANCH}"
CHECKSUM=$(find . -type f -exec md5sum {} \; | sort -k 2 | md5sum | cut -d" " -f 1)
echo "CHECKSUM=${CHECKSUM}" > "${CONTAINERS_FILE}"
git add "${CONTAINERS_FILE}"
git commit -m "${COMMIT_MESSAGE}"
git push "${REPOSITORY_REMOTE}" "${REPOSITORY_DEFAULT_BRANCH}"
