# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

FROM ubuntu:focal

RUN apt-get update -q=2 && \
    apt-get install -q=2 --no-install-recommends python3-pip gunicorn git

COPY requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt

COPY . /conductor-build/
RUN cd /conductor-build/ && python3 setup.py install
RUN rm -rf /conductor-build/
RUN conductor-admin collectstatic
RUN useradd -U conductor
