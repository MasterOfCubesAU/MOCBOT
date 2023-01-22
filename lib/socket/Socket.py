from glob import glob
import os
import sys
from aiohttp import web
import socketio
import logging
from discord.ext import commands
import yaml

with open("./config.yml", "r") as f:
    config = yaml.safe_load(f)

SIO = socketio.AsyncServer(cors_allowed_origins = [f'http://[{config["SOCKET"]["HOST"]}:{config["SOCKET"]["PORT"]}'])
APP = web.Application()
RUNNER = web.AppRunner(APP)
SIO.attach(APP)

class Socket():
    
    HOST = config["SOCKET"]["HOST"]
    PORT = config["SOCKET"]["PORT"]

    async def start(bot: commands.Bot):
        await bot.wait_until_ready()
        namespaces = [path.split("\\")[-1][:-3] if os.name == "nt" else path.split("\\")[-1][:-3].split("/")[-1] for path in glob("./lib/socket/namespaces/*.py")]
        for namespace in namespaces:
            exec(f"from .namespaces.{namespace} import {namespace}")
            SIO.register_namespace(eval(namespace)((f'/{namespace.lower()}')))
            logging.getLogger(__name__).info(f"Initialized /{namespace.lower()} namespace")
        await RUNNER.setup()
        site = web.TCPSite(RUNNER, Socket.HOST, Socket.PORT)
        await site.start()
        logging.getLogger(__name__).info(f"[SOCKET] Listening on {Socket.HOST}:{Socket.PORT}")

    @SIO.event
    async def message(socketID, data):
        logging.getLogger(__name__).info(f"{socketID} sent message: {data}")

    @SIO.event
    async def disconnect(socketID):
       logging.getLogger(__name__).info(f"{socketID} has disconnected")

    
    @staticmethod
    async def emit(*args, **kwargs):
        await SIO.emit(*args, **kwargs)