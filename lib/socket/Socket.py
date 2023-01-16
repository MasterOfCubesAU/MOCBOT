from aiohttp import web
import socketio
import logging
from discord.ext import commands
from socketio.exceptions import ConnectionRefusedError
from hashlib import sha256
import yaml
import sys
if 'Verification' in sys.modules:
    from lib.cogs.Verification import Verification

SIO = socketio.AsyncServer(cors_allowed_origins = '*')
APP = web.Application()
RUNNER = web.AppRunner(APP)
SIO.attach(APP)

with open("./config.yml", "r") as f:
    config = yaml.safe_load(f)
class Socket():
    
    HOST = "0.0.0.0"
    PORT = 65534

    async def start(bot: commands.Bot):
        await bot.wait_until_ready()
        await RUNNER.setup()
        site = web.TCPSite(RUNNER, Socket.HOST, Socket.PORT)
        await site.start()
        logging.getLogger(__name__).info(f"[SOCKET] Listening on {Socket.HOST}:{Socket.PORT}")

    @SIO.event
    async def connect(clientID, environ):
        socketKey = environ.get("HTTP_SOCKET_KEY")
        if socketKey is None or (socketKey is not None and sha256(socketKey.encode('utf-8')).hexdigest() != config["SOCKET_KEY"]):
            logging.getLogger(__name__).warning(f"Unauthorised connection from {environ.get('REMOTE_ADDR', None)}")
            raise ConnectionRefusedError("Unauthorised")
        logging.getLogger(__name__).info(f"Connection established with {clientID}")

    @SIO.event(namespace='/verification')
    async def on_verify_user(clientID, data):
        Verification.web_verify_user(data.member, data.captcha)

    @SIO.event
    async def message(clientID, data):
        logging.getLogger(__name__).info(f"{clientID} sent message: {data}")

    @SIO.event
    async def disconnect(clientID):
       logging.getLogger(__name__).info(f"{clientID} has disconnected")

    @staticmethod
    async def emit_to_client(event, data=None):
        await SIO.emit(event, data)
