from aiohttp import web
import socketio
import logging
from discord.ext import commands

SIO = socketio.AsyncServer()
APP = web.Application()
RUNNER = web.AppRunner(APP)
SIO.attach(APP)


class Socket():
    
    HOST = "localhost"
    PORT = 65534
        
    @SIO.event
    async def connect(clientID, environ):
        logging.getLogger(__name__).info(f"Connection established with {clientID}")

    @SIO.event
    async def message(clientID, data):
        logging.getLogger(__name__).info(f"{clientID} sent message: {data}")

    @SIO.event
    async def disconnect(clientID):
       logging.getLogger(__name__).info(f"{clientID} has disconnected")

    @staticmethod
    async def start(bot: commands.Bot):
        await bot.wait_until_ready()
        await RUNNER.setup()
        site = web.TCPSite(RUNNER, Socket.HOST, Socket.PORT)
        await site.start()
        logging.getLogger(__name__).info(f"[SOCKET] Listening on {Socket.HOST}:{Socket.PORT}")
