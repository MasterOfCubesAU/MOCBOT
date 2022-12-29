from discord.ext import commands
from discord.ui import View
from APIHandler import API

import discord
import logging

class Guilds(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")
        
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        view=View()
        view.add_item(discord.ui.Button(label="Setup",style=discord.ButtonStyle.link,url=f"https://mocbot.masterofcubesau.com/{guild.id}/manage"))
        await guild.owner.send(embed=self.bot.create_embed("MOCBOT SETUP", f"To ensure full functionality of {self.bot.user.mention}, you must setup the bot to accomodate your server.", None), view=view)


    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        API.delete(f'/settings/{guild.id}')

async def setup(bot):
    await bot.add_cog(Guilds(bot))
