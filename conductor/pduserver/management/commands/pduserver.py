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
import zmq
import zmq.asyncio
from aiohttp import web
from asgiref.sync import sync_to_async
from conductor.core.models import PDUAgent
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from zmq.utils.strtypes import u


async def zmq_message_forward(app):
    logger = app["logger"]
    context = zmq.asyncio.Context()
    logger.info("Create pull  socket at %r", settings.INTERNAL_ZMQ_SOCKET)
    pull = context.socket(zmq.PULL)
    pull.bind(settings.INTERNAL_ZMQ_SOCKET)

    async def forward_message(msg):
        data = [s.decode("utf-8") for s in msg]
        app["logger"].debug("Forwarding: %s", data[0])
        message = json.loads(data[2])
        agent_name = message["agent"]
        agent_ws = app["agents"].get(agent_name)
        if agent_ws is not None:
            await agent_ws.send_json(message)
            app["logger"].debug("Message: %s sent", data[0])
            app["logger"].debug("%s", message)

    with contextlib.suppress(asyncio.CancelledError):
        logger.info("waiting for events")
        while True:
            try:
                msg = await pull.recv_multipart()
                await forward_message(msg)
            except zmq.error.ZMQError as exc:
                logger.error("Received a ZMQ error: %s", exc)

    endpoint = u(pull.getsockopt(zmq.LAST_ENDPOINT))
    pull.unbind(endpoint)

    def signal_handler(*_):
        logger.debug("Exiting in a moment...")

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)

    while True:
        try:
            msg = await asyncio.wait_for(pull.recv_multipart(), settings.INTERNAL_ZMQ_TIMEOUT)
            await forward_message(msg)
        except zmq.error.ZMQError as exc:
            logger.error("Received a ZMQ error: %s", exc)
        except asyncio.TimeoutError:
            logger.info("Timing out")
            break

    pull.close(linger=1)
    context.term()


async def websocket_handler(request):
    logger = request.app["logger"]
    logger.info(f"connection from {request.remote}")

    ws = web.WebSocketResponse()
    logger.info("Prepare ws")
    await ws.prepare(request)
    logger.info("After prepare")
    # check if client authenticates properly
    auth = request.headers.get("Authorization")
    if auth:
        logger.debug("Received request with Authorization")
        token = auth.split(":")[1].strip()
        try:
            agent = await sync_to_async(PDUAgent.objects.get, thread_sensitive=True)(token=token)
            logger.info(f"Agent {agent.name} connected")
            if agent.name in request.app["agents"].keys():
                await ws.send_json({"error": "already logged in"})
            request.app["agents"][agent.name] = ws
            agent.state = PDUAgent.STATE_ONLINE
            await sync_to_async(agent.save, thread_sensitive=True)()
            if agent.message:
                logger.debug(f"Sending msg {agent.message} to {agent.name}")
                await ws.send_json({"msg": agent.message})
                agent.message = None
                await sync_to_async(agent.save, thread_sensitive=True)()
            try:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.ERROR:
                        logger.exception(ws.exception())
                    if msg.type == aiohttp.WSMsgType.CLOSE:
                        request.app["agents"].pop(agent.name)
                        logger.info("Removed {agent.name}")
            except asyncio.exceptions.CancelledError:
                request.app["agents"].pop(agent.name)
                logger.info("Removed {agent.name} on exception")

        except PDUAgent.DoesNotExist:
            # ignore unathorized request
            pass
        finally:
            if not request.app["in_shutdown"]:
                await ws.close()
                logger.info(f"connection closed from {request.remote}({agent.name})")
                if agent.name in request.app["agents"].keys():
                    request.app["agents"].pop(agent.name)
                agent.state = PDUAgent.STATE_OFFLINE
                await sync_to_async(agent.save, thread_sensitive=True)()

    return ws


async def on_shutdown(app):
    logger = app["logger"]
    app["in_shutdown"] = True
    for name, ws in app["agents"].items():
        logger.debug(name)
        await ws.close(code=aiohttp.WSCloseCode.GOING_AWAY, message="Server shutdown")
        try:
            agent = await sync_to_async(PDUAgent.objects.get, thread_sensitive=True)(name=name)
            agent.state = PDUAgent.STATE_OFFLINE
            await sync_to_async(agent.save, thread_sensitive=True)()
            logger.debug("Turning %s offline" % name)
        except PDUAgent.DoesNotExist:
            pass


async def on_startup(app):
    app["zmq"] = asyncio.create_task(zmq_message_forward(app))


class Command(BaseCommand):
    help = "Runs websocket server for agents"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--host", default="*", help="Hostname")
        parser.add_argument("--port", default=8001, type=int, help="Port")
        parser.add_argument("--logfile", default="-", help="Path to logfile")

    def handle(self, *args, **options):
        self.logger = logging.getLogger("pduserver")
        if options["verbosity"] == 0:
            self.logger.setLevel(logging.ERROR)
        elif options["verbosity"] == 1:
            self.logger.setLevel(logging.WARN)
        elif options["verbosity"] == 2:
            self.logger.setLevel(logging.INFO)
        elif options["verbosity"] == 3:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.DEBUG)

        if options["logfile"] != "-":
            handler = logging.handlers.WatchedFileHandler(options["logfile"])
            self.logger.addHandler(handler)

        self.logger.info("Starting pduserver")
        # Create the aiohttp application
        app = web.Application()

        # Variables
        app["logger"] = self.logger
        app["agents"] = {}
        app["in_shutdown"] = False

        # Routes
        app.add_routes([web.get("/ws/", websocket_handler)])

        # signals
        app.on_shutdown.append(on_shutdown)
        app.on_startup.append(on_startup)

        # Run the application
        self.logger.info(
            "Listening on http://%s:%d", options["host"], options["port"]
        )
        web.run_app(app, host=options["host"], port=options["port"], print=False)
