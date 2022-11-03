from discord.ext import commands, tasks
from discord.ui import Button, View
from discord import app_commands
from lib.bot import config, MOCBOT, DEV_GUILD, MOC_DB
from typing import Literal, Union, Optional

import discord
import logging

from itertools import cycle

class Status(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.statuschange.start()
        self.logger = logging.getLogger(__name__)

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")  

    def cog_unload(self):
        self.statuschange.stop()

    @tasks.loop(minutes=2)
    async def statuschange(self):
        await self.bot.change_presence(activity=discord.Game(next(self.statuses)))

    @statuschange.before_loop
    async def before_statuschange(self):
        await self.bot.wait_until_ready()
        self.statuses = cycle([self.bot.get_user(self.bot.owner_id)] + [self.bot.get_user(id) for id in config["DEVELOPERS"]] + ["masterofcubesau.com"])

async def setup(bot):
    await bot.add_cog(Status(bot))
