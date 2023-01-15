import asyncio
from aiohttp import web
import socketio
from discord.ext import commands
import logging

sio = socketio.AsyncServer()
app = web.Application()
sio.attach(app)

class Socket(commands.Cog):
    def __init__(self, bot):
        self.logger = logging.getLogger(__name__)
        web.run_app(app)

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")

    @sio.event
    async def connect(sid, environ):
        print('connection established', sid)

    @sio.event
    async def my_message(sid, data):
        print('message received with ', data)

    @sio.event
    async def disconnect(sid):
        print('disconnected from server', sid)

async def setup(bot):
    await bot.add_cog(Socket(bot))