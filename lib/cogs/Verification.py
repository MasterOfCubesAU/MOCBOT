
from discord.ext import commands
from utils.APIHandler import API
from discord import app_commands, Member, Object, Interaction, Forbidden, HTTPException
from typing import Optional
from lib.bot import DEV_GUILD
from enum import Enum
from lib.socket.Socket import Socket
from requests.exceptions import HTTPError
import logging
from discord.ui import Button, View
import discord
import datetime

class VerificationStatus(Enum):
    SUCCESS = 1,
    LOCKDOWN = 2,
    ERROR = 3,

class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    def reload_cogs(self):
        self.logger.info(f"[COG] Reloaded {self.__class__.__name__}")

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")

    @staticmethod
    async def web_verify_user(userID: str, guildID:str, captcha=None):
        settings = API.get(f'/settings/{guildID}')
        guild = await Verification.bot.fetch_guild(guildID)
        member = await guild.fetch_member(userID)
        if not bool(settings.get("Verification", None) if settings is not None else False):
            return await Socket.emit("verify_error", namespace="/verification")
        match await Verification.verify_user(member, settings.get("Verification"), captcha):
            case VerificationStatus.SUCCESS:
                await Socket.emit("verify_success", namespace="/verification")
            case VerificationStatus.LOCKDOWN:
                await Socket.emit("verify_lockdown", namespace="/verification")
            case VerificationStatus.ERROR:
                await Socket.emit("verify_error", namespace="/verification")

    @staticmethod
    async def verify_user(member: Member, settings: Object, captcha=None):
        if int(settings.get("VerificationRoleID")) in [role.id for role in member.roles] and len(member.roles) == 2:
            if captcha is None or (captcha is not None and captcha["score"] >= 0.7):
                try:
                    await member.remove_roles(Object(id=settings.get("VerificationRoleID")), reason=f"{member} successfully verified")
                    await member.add_roles(Object(id=settings.get("VerifiedRoleID")), reason=f"{member} successfully verified")
                except HTTPException:
                    return VerificationStatus.ERROR
                else:
                    try:
                        await member.send(embed=Verification.bot.create_embed("MOCBOT VERIFICATION", f"You have been successfully verified in **{member.guild}**. Enjoy your stay!", None))
                    except (HTTPException, Forbidden):
                        pass
                    API.delete(f'/verification/{member.guild.id}/{member.id}')
                return VerificationStatus.SUCCESS
            else:
                try:
                    await member.remove_roles(Object(id=settings.get("VerificationRoleID")), reason=f"{member} placed in lockdown")
                    await member.add_roles(Object(id=settings.get("LockdownRoleID")))
                except HTTPException:
                    return VerificationStatus.ERROR
                else:
                    guild = await Verification.bot.fetch_guild(member.guild.id)
                    channel = await guild.fetch_channel(int(settings.get("LockdownApprovalsChannelID")))
                    view=View()
                    view.add_item(Button(label="View dashboard",style=discord.ButtonStyle.link,url=f"https://mocbot.masterofcubesau.com/{member.guild.id}/manage/verification"))
                    message = await channel.send(embed=Verification.bot.create_embed("MOCBOT VERIFICATION", f"The user {member.mention} has recently attempted to join your server and has been placed into lockdown. This usually indicates that the user is suspicious, however, this may be a false call and manual admin approval is required.\n\n **To manually verify this user, please visit the MOCBOT Dashboard below.**", None), view=view)
                    try:
                        await member.send(embed=Verification.bot.create_embed("MOCBOT VERIFICATION", f"You have been placed into lockdown in the **{member.guild}** server. This occurs because you did not pass verification, however this can be a false call. If you believe this is a mistake, please contact a server moderator for approval.", None))
                    except (HTTPException, Forbidden):
                        pass 
                    API.patch(f'/verification/{member.guild.id}/{member.id}', {"MessageID": message.id, "ChannelID": channel.id})
                    return VerificationStatus.LOCKDOWN
        return VerificationStatus.ERROR
                    
    @commands.Cog.listener()
    async def on_member_join(self, member: Member):
        settings = API.get(f'/settings/{member.guild.id}').get("Verification")
        if settings is None:
            return
        # try:
        #     user = API.get(f'/verification/{member.guild.id}/{member.id}')
        # except HTTPError as e:
        #     if e.response.status_code == 404:
        #         pass
        #     else:
        #         raise e 
        # else:
        #     user_join_time = user.get("JoinTime") if user is not None else None
        #     if user_join_time is not None and (datetime.datetime.fromtimestamp(user_join_time) + datetime.timedelta(days=7).timestamp()) < datetime.now():
        #         guild = self.bot.get_guild(member.guild.id)
        #         try:
        #             await member.send(embed=Verification.bot.create_embed("MOCBOT VERIFICATION", f"You have been in lockdown in the {member.guild} server for more than 7 days, and thus have been kicked. Please contact {guild.owner} if you believe this is a mistake.", None))
        #         except (HTTPException, Forbidden):
        #             pass 
        #         await guild.kick(member, reason="User in lockdown for more than 7 days.")
        # finally:
        await member.add_roles(Object(id=settings.get("VerificationRoleID")))
        API.post(f'/verification/{member.guild.id}/{member.id}', {})
        try:
            await member.send(embed=self.bot.create_embed("MOCBOT VERIFICATION", f"**Welcome to {member.guild}!**\n\n To get verified, please click [here](http://localhost:3000/verify/{member.guild.id}/{member.id}).", None))
        except Forbidden:
            pass 

    @app_commands.command(name="verify", description="Re-issues the verify link. If a user is provided (admin only), that user will be verified at once.")
    @app_commands.guilds(DEV_GUILD)
    async def verify(self, interaction: Interaction, user: Optional[Member]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        settings = API.get(f'/settings/{interaction.guild.id}')
        if not bool(settings.get("Verification") if settings is not None else False):
            return await interaction.followup.send(embed=self.bot.create_embed("MOCBOT VERIFICATION", f"This command has been disabled in **{interaction.guild}.**", None))
        verification_roles = settings.get("Verification")

        if user is not None:
            if not interaction.permissions.manage_guild:
                return await interaction.followup.send(embed=self.bot.create_embed("MOCBOT VERIFICATION", "You are missing the required permissions to execute that command!\n\nIf you wish to be verified, please contact a server moderator, or type `/verify` without additional inputs.", None))
            match await Verification.verify_user(user, verification_roles):
                case VerificationStatus.SUCCESS:
                    return await interaction.followup.send(embed=self.bot.create_embed("MOCBOT VERIFICATION", f"{user.mention} has successfully been verified.", None))
                case VerificationStatus.ERROR:
                    return await interaction.followup.send(embed=self.bot.create_embed("MOCBOT VERIFICATION", f"Something went wrong when verifying {user.mention}.", None))
        else:
            if int(verification_roles.get("VerifiedRoleID")) in [role.id for role in interaction.user.roles]:
                await interaction.followup.send(embed=self.bot.create_embed("MOCBOT VERIFICATION", f"You are already verified in this server.", None))
            else:
                await interaction.followup.send(embed=self.bot.create_embed("MOCBOT VERIFICATION", f"**Welcome to {interaction.guild}!**\n\n To get verified, please click [here](http://localhost:3000/verify/{interaction.guild.id}/{interaction.user.id}).", None))

async def setup(bot):
    Verification.bot = bot
    await bot.add_cog(Verification(bot))
