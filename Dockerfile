FROM ubuntu:focal

RUN apt-get update -q=2 && \
    apt-get install -q=2 --no-install-recommends python3-pip gunicorn

COPY requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt

COPY . /conductor-build/
RUN cd /conductor-build/ && python3 setup.py install
ENV CONDUCTOR_CELERY_BROKER_URL="amqp://conductor:secret@172.17.0.1/conductor"
RUN rm -rf /conductor-build/
COPY entrypoint.sh /root/
ENTRYPOINT ["/root/entrypoint.sh"]
