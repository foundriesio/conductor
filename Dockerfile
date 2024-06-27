# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

FROM ubuntu:22.04

RUN apt-get update -q=2 && \
    apt-get install -q=2 --no-install-recommends python3-pip gunicorn git curl jq

COPY requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt

# install conductor
COPY . /conductor-build/
RUN cd /conductor-build/ && python3 setup.py install
RUN rm -rf /conductor-build/
RUN conductor-admin collectstatic

# install fioctl
RUN FIOCTL_VERSION=$(curl -L -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" https://api.github.com/repos/foundriesio/fioctl/releases | jq -r '.[0].tag_name') && \
    curl -o /usr/local/bin/fioctl -LO https://github.com/foundriesio/fioctl/releases/download/$FIOCTL_VERSION/fioctl-linux-amd64 && \
	chmod a+x /usr/local/bin/fioctl

RUN useradd -U conductor
