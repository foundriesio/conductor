#!/bin/bash

# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

REPOSITORY_DIR=""
REPOSITORY_REMOTE=origin
REPOSITORY_LMP_REMOTE=lmp
REPOSITORY_LMP_BRANCH=main
REPOSITORY_DEFAULT_BRANCH=main

usage() {
    echo "Usage: $0 [-d <repository_dir>] [-r <repository_remote>] [-t <lmp remote branch>]
                    [-l <lmp manifest remote>] [-b <repository default branch name>]" 1>&2
    exit 1
}

while getopts "d:r:l:b:t:" o; do
  case "$o" in
    # The current working directory will be used by default.
    # Use '-p' specify partition that used for fio test.
    d) REPOSITORY_DIR="${OPTARG}" ;;
    r) REPOSITORY_REMOTE="${OPTARG}" ;;
    l) REPOSITORY_LMP_REMOTE="${OPTARG}" ;;
    t) REPOSITORY_LMP_BRANCH="${OPTARG}" ;;
    b) REPOSITORY_DEFAULT_BRANCH="${OPTARG}";;
    *) usage ;;
  esac
done

git_merge(){
    git merge -X theirs  --no-edit -m "update-manifest: merge LmP ${REPOSITORY_LMP_BRANCH} to ${REPOSITORY_DEFAULT_BRANCH}" "${REPOSITORY_LMP_REMOTE}/${REPOSITORY_LMP_BRANCH}"
}

git_merge_fix_keys_conflict(){
    git rm -r conf/keys && \
    git commit -m "update-manifest: merge LmP main to main (key conflict)"
}

cd "${REPOSITORY_DIR}"
git checkout "${REPOSITORY_DEFAULT_BRANCH}"
git fetch --all
git_merge || git_merge_fix_keys_conflict || exit $?
git push "${REPOSITORY_REMOTE}" "${REPOSITORY_DEFAULT_BRANCH}"
