#!/bin/bash

REPOSITORY_DIR=""
REPOSITORY_REMOTE=origin
REPOSITORY_LMP_REMOTE=lmp

usage() {
    echo "Usage: $0 [-d <repository_dir>] [-r <repository_remote>]
                    [-l <lmp manifest remote>]" 1>&2
    exit 1
}

while getopts "d:r:l:" o; do
  case "$o" in
    # The current working directory will be used by default.
    # Use '-p' specify partition that used for fio test.
    d) REPOSITORY_DIR="${OPTARG}" ;;
    r) REPOSITORY_REMOTE="${OPTARG}" ;;
    l) REPOSITORY_LMP_REMOTE="${OPTARG}" ;;
    *) usage ;;
  esac
done

cd "${REPOSITORY_DIR}"
git checkout master
git fetch --all
git merge -X theirs  --no-edit -m "update-manifest: merge LmP master" "${REPOSITORY_LMP_REMOTE}"/master || exit $?
git push "${REPOSITORY_REMOTE}" master
