#!/bin/bash

REPOSITORY_DIR=""
REPOSITORY_REMOTE=origin
COMMIT_MESSAGE="upgrade/rollback testing"

usage() {
    echo "Usage: $0 [-d <repository_dir>] [-r <repository_remote>]
                    [-m <commit message>]" 1>&2
    exit 1
}

while getopts "d:r:m:" o; do
  case "$o" in
    # The current working directory will be used by default.
    # Use '-p' specify partition that used for fio test.
    d) REPOSITORY_DIR="${OPTARG}" ;;
    r) REPOSITORY_REMOTE="${OPTARG}" ;;
    m) COMMIT_MESSAGE="${OPTARG}" ;;
    *) usage ;;
  esac
done

cd "${REPOSITORY_DIR}"
git checkout master
git commit --allow-empty -m "${COMMIT_MESSAGE}"
git push "${REPOSITORY_REMOTE}" master
