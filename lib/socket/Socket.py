from glob import glob
import os
import sys
from aiohttp import web
import socketio
import logging
from discord.ext import commands

SIO = socketio.AsyncServer(cors_allowed_origins = '*')
APP = web.Application()
RUNNER = web.AppRunner(APP)
SIO.attach(APP)

class Socket():
    
    HOST = "0.0.0.0"
    PORT = 65534

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