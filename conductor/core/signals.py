# Copyright 2021 Foundries.io
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import logging
import uuid
import zmq
from conductor.core.models import PDUAgent, Project
from conductor.core.tasks import create_project_repository
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from zmq.utils.strtypes import b


logger = logging.getLogger()


def send_message(topic, data):
    context = zmq.Context.instance()
    socket = context.socket(zmq.PUSH)
    socket.connect(settings.INTERNAL_ZMQ_SOCKET)

    try:
        msg = [
            b(str(uuid.uuid1())),
            b(datetime.datetime.utcnow().isoformat()),
            b(json.dumps(data)),
        ]
        logger.debug(f"Sending message {data} to {settings.INTERNAL_ZMQ_SOCKET}")
        socket.send_multipart(msg, zmq.DONTWAIT)
        logger.debug("Message sent")
    except (TypeError, ValueError, zmq.ZMQError):
        logger.error("Message sending failed %s" % (settings.EVENT_TOPIC + topic))


@receiver(post_save, sender=PDUAgent)
def on_pduagent_save(sender, instance, created, **kwargs):
    if instance.message:
        data = {
            "agent": str(instance.name),
            "cmd": str(instance.message),
        }
        logger.debug(f"Sending message with data {data}")
        send_message(".pduagent", data)
        instance.message = None
        instance.save()


@receiver(post_save, sender=Project)
def on_project_save(sender, instance, created, **kwargs):
    #if created:
    #    create_project_repository.delay(instance.id)
    create_project_repository.delay(instance.id)
