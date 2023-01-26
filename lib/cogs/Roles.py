import traceback
from discord.ext import commands
import logging
from discord import Member, Object, HTTPException

from utils.APIHandler import API
from requests.exceptions import HTTPError

class Roles(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")

    @staticmethod
    async def give_join_roles(member: Member):
        try:
            rolesData = API.get(f'/roles/{member.guild.id}')
        except HTTPError as e:
            if e.response.status_code == 404:
                return
            else:
                raise e 
        if rolesData and rolesData.get("JoinRoles"):
            for roleID in rolesData.get("JoinRoles"):
                try:
                    await member.add_roles(Object(id=int(roleID)), reason="Join Role")
                except HTTPException as e:
                    continue

    @commands.Cog.listener()
    async def on_member_join(self, member: Member):
        settingsData = API.get(f'/settings/{member.guild.id}')
        if "Verification" not in settingsData.get("EnabledModules"):
            await Roles.give_join_roles(member)
      


async def setup(bot):
    await bot.add_cog(Roles(bot))
