#!/bin/bash

# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

REPOSITORY_DIR=""
REPOSITORY_URL=""
REPOSITORY_REMOTE=origin
REPOSITORY_LMP_URL="https://github.com/foundriesio/lmp-manifest"
REPOSITORY_LMP_REMOTE=lmp
REPOSITORY_TOKEN=""
REPOSITORY_DEFAULT_BRANCH=master
REPOSITORY_TYPE=manifest
REPOSITORY_DOMAIN="foundries.io"
UNIT_TEST=""

usage() {
    echo "Usage: $0 [-d <repository_dir>]
                    [-r <repository remote name>]
                    [-u <repository_url>]
                    [-l <lmp manifest remote name>]
                    [-w <lmp maynifest url>]
                    [-t <repository token>]
                    [-c <repository type>]" 1>&2
    exit 1
}

while getopts "d:r:l:u:w:t:b:c:D:f:" o; do
  case "$o" in
    # The current working directory will be used by default.
    # Use '-p' specify partition that used for fio test.
    d) REPOSITORY_DIR="${OPTARG}" ;;
    r) REPOSITORY_REMOTE="${OPTARG}" ;;
    u) REPOSITORY_URL="${OPTARG}" ;;
    l) REPOSITORY_LMP_REMOTE="${OPTARG}" ;;
    w) REPOSITORY_LMP_URL="${OPTARG}" ;;
    t) REPOSITORY_TOKEN="${OPTARG}" ;;
    b) REPOSITORY_DEFAULT_BRANCH="${OPTARG}";;
    c) REPOSITORY_TYPE="${OPTARG}";;
	D) REPOSITORY_DOMAIN="${OPTARG}";;
	f) UNIT_TEST="${OPTARG}";;
    *) usage ;;
  esac
done

cd "${REPOSITORY_DIR}"
# check if the repository is initiated already with proper settings
REMOTE_ORIGIN=$(git remote get-url "${REPOSITORY_REMOTE}")
if [ "${REMOTE_ORIGIN}" = "${REPOSITORY_URL}" ]; then
    # Update the repository token
    git config "http.https://source.${REPOSITORY_DOMAIN}.extraheader" "Authorization: basic $(echo -n $REPOSITORY_TOKEN | openssl base64)"
    exit 0
fi
git init
if [ -n "${UNIT_TEST}" ]; then
    # only run git init for unit tests
    exit 0
fi
git config "http.https://source.${REPOSITORY_DOMAIN}.extraheader" "Authorization: basic $(echo -n $REPOSITORY_TOKEN | openssl base64)"
git config user.email "testbot@foundries.io"
git config user.name "Testbot"
git remote add "${REPOSITORY_REMOTE}" "${REPOSITORY_URL}"
git pull "${REPOSITORY_REMOTE}" "${REPOSITORY_DEFAULT_BRANCH}"
if [ "${REPOSITORY_TYPE}" = "manifest" ]; then
    git remote add "${REPOSITORY_LMP_REMOTE}" "${REPOSITORY_LMP_URL}"
fi
