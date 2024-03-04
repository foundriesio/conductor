#!/bin/bash

# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

REPOSITORY_DIR=""
REPOSITORY_REMOTE=origin
COMMIT_MESSAGE="upgrade/rollback testing"
REPOSITORY_DEFAULT_BRANCH=master
KERNEL_REBUILD="false"

usage() {
    echo "Usage: $0 [-d <repository_dir>] [-r <repository_remote>]
                    [-m <commit message>] [-b <repository default branch name>]
                    [-k <true|false> ]
                    " 1>&2
    exit 1
}

while getopts "d:r:m:b:k:" o; do
  case "$o" in
    # The current working directory will be used by default.
    # Use '-p' specify partition that used for fio test.
    d) REPOSITORY_DIR="${OPTARG}" ;;
    r) REPOSITORY_REMOTE="${OPTARG}" ;;
    m) COMMIT_MESSAGE="${OPTARG}" ;;
    b) REPOSITORY_DEFAULT_BRANCH="${OPTARG}";;
    k) KERNEL_REBUILD="${OPTARG}";;
    *) usage ;;
  esac
done

cd "${REPOSITORY_DIR}"
git checkout "${REPOSITORY_DEFAULT_BRANCH}"
git pull "${REPOSITORY_REMOTE}" "${REPOSITORY_DEFAULT_BRANCH}"
if [ "${KERNEL_REBUILD}" = "true" ] || [ "${KERNEL_REBUILD}" = "True" ] || [ "${KERNEL_REBUILD}" = "TRUE" ]; then
    if [ -d factory-keys ]; then
        # change kernel module keys to force new kernel build
        openssl req -new -nodes -utf8 -sha256 -days 36500 -batch -x509 \
            -config ./conf/keys/x509.genkey -outform PEM \
            -out ./factory-keys/x509_modsign.crt \
            -keyout ./factory-keys/privkey_modsign.pem || true
        git add -u
    fi
fi
git commit --allow-empty -m "${COMMIT_MESSAGE}"
git push "${REPOSITORY_REMOTE}" "${REPOSITORY_DEFAULT_BRANCH}"
