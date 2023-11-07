#!/bin/bash

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

cd "${REPOSITORY_DIR}"
git checkout "${REPOSITORY_DEFAULT_BRANCH}"
git fetch --all
git merge -X theirs  --no-edit -m "update-manifest: merge LmP master" "${REPOSITORY_LMP_REMOTE}/${REPOSITORY_LMP_BRANCH}" || exit $?
git push "${REPOSITORY_REMOTE}" "${REPOSITORY_DEFAULT_BRANCH}"
