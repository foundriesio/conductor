#!/bin/bash

REPOSITORY_DIR=""
REPOSITORY_URL=""
REPOSITORY_REMOTE=origin
REPOSITORY_LMP_URL="https://github.com/foundriesio/lmp-manifest"
REPOSITORY_LMP_REMOTE=lmp
REPOSITORY_TOKEN=""

usage() {
    echo "Usage: $0 [-d <repository_dir>]
                    [-r <repository remote name>]
                    [-u <repository_url>]
                    [-l <lmp manifest remote name>]
                    [-w <lmp manifest url>]
                    [-t <repository token>]" 1>&2
    exit 1
}

while getopts "d:r:l:u:w:t:" o; do
  case "$o" in
    # The current working directory will be used by default.
    # Use '-p' specify partition that used for fio test.
    d) REPOSITORY_DIR="${OPTARG}" ;;
    r) REPOSITORY_REMOTE="${OPTARG}" ;;
    u) REPOSITORY_URL="${OPTARG}" ;;
    l) REPOSITORY_LMP_REMOTE="${OPTARG}" ;;
    w) REPOSITORY_LMP_URL="${OPTARG}" ;;
    t) REPOSITORY_TOKEN="${OPTARG}" ;;
    *) usage ;;
  esac
done

cd "${REPOSITORY_DIR}"
# check if the repository is initiated already with proper settings
REMOTE_ORIGIN=$(git remote get-url "${REPOSITORY_REMOTE}")
REMOTE_LMP=$(git remote get-url "${REPOSITORY_LMP_REMOTE}")
if [ "${REMOTE_ORIGIN}" = "${REPOSITORY_URL}" ] && [ "${REMOTE_LMP}" = "${REPOSITORY_LMP_URL}" ]; then
    # exit the script, nothing to do
    exit 0
fi
git init
git config http.https://source.foundries.io.extraheader "Authorization: basic $(echo -n $REPOSITORY_TOKEN | openssl base64)"
git config user.email "testbot@foundries.io"
git config user.name "Testbot"
git remote add "${REPOSITORY_REMOTE}" "${REPOSITORY_URL}"
git pull "${REPOSITORY_REMOTE}" master
git remote add "${REPOSITORY_LMP_REMOTE}" "${REPOSITORY_LMP_URL}"
