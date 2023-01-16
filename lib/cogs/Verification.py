
from discord.ext import commands
from utils.APIHandler import API
from discord import app_commands, Member, Object, Interaction, Forbidden
from typing import Optional
from lib.bot import DEV_GUILD
from enum import Enum
from lib.socket.Socket import Socket
import logging

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
        # TODO: Call API to update/delete user based on returned enum
        if int(settings.get("VerificationRoleID")) in [role.id for role in member.roles] and len(member.roles) == 2:
            if captcha is None or (captcha is not None and captcha["score"] >= 0.7):
                await member.remove_roles(Object(id=settings.get("VerificationRoleID")), reason=f"{member} successfully verified")
                await member.add_roles(Object(id=settings.get("VerifiedRoleID")), reason=f"{member} successfully verified")
                await member.send(embed=Verification.bot.create_embed("MOCBOT VERIFICATION", f"You have been successfully verified in **{member.guild}**. Enjoy your stay!", None))
                return VerificationStatus.SUCCESS
            else:
                await member.remove_roles(Object(id=settings.get("VerificationRoleID")), reason=f"{member} placed in lockdown")
                await member.add_roles(Object(id=settings.get("LockdownRoleID")))
                await member.send("You have successfully been locked down.")
                return VerificationStatus.LOCKDOWN
        return VerificationStatus.ERROR
                    
    @commands.Cog.listener()
    async def on_member_join(self, member: Member):
        settings = API.get(f'/settings/{member.guild.id}').get("Verification")
        if settings is None:
            return
        # TODO:
        # Check if user is in lockdown => kick user
        await member.add_roles(Object(id=settings.get("VerificationRoleID")))
        API.post(f'/verification/{member.guild.id}/{member.id}', {})
        try:
            await member.send(embed=self.bot.create_embed("MOCBOT VERIFICATION", f"**Welcome to {member.guild}!**\n\n To get verified, please click [here](http://localhost:3000/verify/{member.guild.id}/{member.id})", None))
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
                    return await interaction.followup.send(embed=self.bot.create_embed("MOCBOT VERIFICATION", f"{user.mention} is not currently in verification.", None))
        else:
            if int(verification_roles.get("VerifiedRoleID")) in [role.id for role in interaction.user.roles]:
                await interaction.followup.send(embed=self.bot.create_embed("MOCBOT VERIFICATION", f"You are already verified in this server.", None))
            else:
                await interaction.followup.send(embed=self.bot.create_embed("MOCBOT VERIFICATION", f"**Welcome to {interaction.guild}!**\n\n To get verified, please click [here](http://localhost:3000/verify/{interaction.guild.id}/{interaction.user.id})", None))

async def setup(bot):
    Verification.bot = bot
    await bot.add_cog(Verification(bot))
