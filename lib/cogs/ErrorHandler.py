from discord.ext import commands
from discord.ui import Button, View
from discord import app_commands
from lib.bot import config, logger, MOCBOT, DEV_GUILD, MOC_DB
from typing import Literal, Union, Optional
import discord

import traceback



class ErrorHandler(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.bot.tree.on_error = self.on_app_command_error

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"[COG] Loaded {self.__class__.__name__}")
        
    async def on_app_command_error(self, interaction, error):
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT ERROR", error, 0xFF0000), ephemeral=True)
        logger.error(f"[ERROR] Interaction Error: {error}")
        traceback.print_exc()




async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))
