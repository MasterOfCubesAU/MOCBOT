from discord.ext import commands
from discord.ui import View
from discord import app_commands
from lib.bot import config, MOCBOT, DEV_GUILD, MOC_DB
from typing import Literal, Union, Optional

import discord
import logging




class Template(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")
        

async def setup(bot):
    await bot.add_cog(Template(bot))
