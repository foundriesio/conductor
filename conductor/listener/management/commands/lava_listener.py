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
import aiohttp
import asyncio
import contextlib
import json
import logging
import signal
import subprocess
import sys
import time

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand
from django.db.models import Field
from django.db.utils import OperationalError

from conductor.core.models import Project
from conductor.core.tasks import process_testjob_notification, process_device_notification


logger = logging.getLogger()


async def listener_main(project):

    event = asyncio.Event()
    await asyncio.gather(
        listen_for_events(event, project)
    )

async def listen_for_events(event: asyncio.Event, project) -> None:
    logger.info("Starting event listener")
    while True:
        with contextlib.suppress(aiohttp.ClientError):
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(project.websocket_url) as ws:
                    logger.info("Session connected")
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            data = json.loads(msg.data)
                            logger.info(data)
                            (topic, _, dt, username, data) = data
                            data = json.loads(data)
                            if topic.endswith(".testjob"):
                                logger.info(f"dispatching testjob {data['job']}")
                                #await sync_to_async(process_testjob_notification.delay, thread_sensitive=True)(data)
                                process_testjob_notification.delay(data)
                            if topic.endswith(".device"):
                                await sync_to_async(process_device_notification.delay, thread_sensitive=True)(data)
                        except ValueError:
                            logger.error("Invalid message: %s", msg)
                            continue
        await asyncio.sleep(1)


class Listener(object):

    def __init__(self, project):
        self.project = project

    def run(self):
        project = self.project
        if not project.websocket_url:
            logger.info("Websocket URL missing. Exiting")
            sys.exit()

        logger.info("Backend %s starting" % project.name)
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        loop.run_until_complete(listener_main(project))
        loop.close()
        logger.info("Backend %s exited on its own" % project.name)

    def stop(self, signal, stack_frame):
        logger.info("Backend %s finishing ..." % self.project.name)
        sys.exit()


class ListenerManager(object):

    def __init__(self):
        self.__processes__ = {}

    def run(self):
        self.setup_signals()
        self.wait_for_setup()
        self.loop()
        self.cleanup()

    def setup_signals(self):
        # make SIGTERM equivalent to SIGINT (e.g. control-c)
        signal.signal(signal.SIGTERM, signal.getsignal(signal.SIGINT))

    def wait_for_setup(self):
        n = 0
        while n < 24:  # wait up to 2 min
            try:
                Project.objects.count()
                logger.info("listener manager started")
                return
            except OperationalError:
                logger.info("Waiting to database to be up; will retry in 5s ...")
                time.sleep(5)
                n += 1
        logger.error("Timed out waiting for database to be up")
        sys.exit(1)

    def keep_listeners_running(self):
        ids = list(self.__processes__.keys())

        for project in Project.objects.all():
            process = self.__processes__.get(project.id)
            if not process:
                self.start(project)
            if project.id in ids:
                ids.remove(project.id)

        # remaining projects were removed from the database, stop them
        for project_id in ids:
            self.stop(project_id)

    def start(self, project):
        argv = [sys.executable, '-m', 'conductor.manage', 'lava_listener', project.name]
        listener = subprocess.Popen(argv)
        self.__processes__[project.id] = listener

    def loop(self):
        try:
            while True:
                self.keep_listeners_running()
                # FIXME: ideally we should have a blocking call here that waits
                # for a change to happen in the database, but we didn't find a
                # simple/portable way of doing that yet. Let's just sleep for a
                # few seconds instead, for now.
                time.sleep(60)
        except KeyboardInterrupt:
            pass  # cleanup() will terminate sub-processes

    def cleanup(self):
        for project_id in list(self.__processes__.keys()):
            self.stop(project_id)

    def stop(self, project_id):
        process = self.__processes__[project_id]
        if not process.poll():
            process.terminate()
            process.wait()
        self.__processes__.pop(project_id)

class Command(BaseCommand):
    help = "Listen to LAVA websocket events"

    def add_arguments(self, parser):
        parser.add_argument(
            'PROJECT',
            nargs='?',
            type=str,
            help='Project name to listen to. If ommited, start the master process.',
        )

    def handle(self, *args, **options):
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        if options['verbosity'] == 0:
            handler.setLevel(logging.WARNING)
        if options['verbosity'] == 1:
            handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.info("Starting lava_listener command")
        project_name = options.get("PROJECT")
        if project_name:
            project = Project.objects.get(name=project_name)
            Listener(project).run()
        else:
            ListenerManager().run()

