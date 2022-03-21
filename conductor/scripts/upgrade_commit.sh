#!/bin/bash

REPOSITORY_DIR=""
REPOSITORY_REMOTE=origin
COMMIT_MESSAGE="upgrade/rollback testing"
REPOSITORY_DEFAULT_BRANCH=master

usage() {
    echo "Usage: $0 [-d <repository_dir>] [-r <repository_remote>]
                    [-m <commit message>] [-b <repository default branch name>]" 1>&2
    exit 1
}

while getopts "d:r:m:b:" o; do
  case "$o" in
    # The current working directory will be used by default.
    # Use '-p' specify partition that used for fio test.
    d) REPOSITORY_DIR="${OPTARG}" ;;
    r) REPOSITORY_REMOTE="${OPTARG}" ;;
    m) COMMIT_MESSAGE="${OPTARG}" ;;
    b) REPOSITORY_DEFAULT_BRANCH="${OPTARG}";;
    *) usage ;;
  esac
done

cd "${REPOSITORY_DIR}"
git checkout "${REPOSITORY_DEFAULT_BRANCH}"
git commit --allow-empty -m "${COMMIT_MESSAGE}"
git push "${REPOSITORY_REMOTE}" "${REPOSITORY_DEFAULT_BRANCH}"
