from discord.ext import commands
from discord.ui import Button, View
from discord import app_commands
from lib.bot import config, logger, MOCBOT, DEV_GUILD, MOC_DB
from typing import Literal, Union, Optional
import discord

from glob import glob
import os


class Cogs(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.disabled_cogs = ["Template"]
        self.unloaded_cogs = []
        self.loaded_cogs = []

    async def fetch_cogs(self):
        for cog in [path.split("\\")[-1][:-3] if os.name == "nt" else path.split("\\")[-1][:-3].split("/")[-1] for path in glob("./lib/cogs/*.py")]:
            if cog != "Cogs" and cog not in self.disabled_cogs:
                self.unloaded_cogs.append(cog)

    async def load_cog(self, cog):
        try:
            await self.bot.load_extension(f"lib.cogs.{cog}")
        except Exception as e:
            logger.error(f"[COG] {cog} failed to load. {e}")

    async def load_cogs(self):
        if not self.unloaded_cogs:
            await self.fetch_cogs()
        while self.unloaded_cogs:
            cog = self.unloaded_cogs.pop(0)
            if cog in config["DEPENDENCIES"]:
                if all([dependency in self.loaded_cogs for dependency in config["DEPENDENCIES"][cog]]):
                    await self.load_cog(cog)
                else:
                    logger.warning(f"[COG] Defferring {cog}")
                    self.unloaded_cogs.append(cog)
            else:
                await self.load_cog(cog)
            


    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"[COG] Loaded {self.__class__.__name__}")

    CogGroup = app_commands.Group(name="cog", description="Manages MOCBOT cogs.", guild_ids=[231230403053092864, 422983658257907732])

    @CogGroup.command(name="list", description="Lists all cog statuses.")
    # @app_commands.checks.has_permissions(manage_guild=True)
    async def list(self, interaction: discord.Interaction):
        embed= self.bot.create_embed("MOCBOT SETUP", None, None)
        embed.add_field(
            name="Enabled",
            value=">>> {}".format("\n".join([x for x in self.bot.cogs])),
            inline=True,
        )
        if bool(self.unloaded_cogs + self.disabled_cogs):
            embed.add_field(
                name="Disabled",
                value=">>> {}".format(
                    "\n".join(self.unloaded_cogs + self.disabled_cogs)
                ),
                inline=True,
            )
        embed.add_field(
            name="\u200b",
            value=f"You may also use the following command to manage cogs.\n> `/cog [load|unload|reload] [*cogs]`",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)



async def setup(bot):
    cogs_class = Cogs(bot)
    await bot.add_cog(cogs_class)
    await cogs_class.load_cogs()