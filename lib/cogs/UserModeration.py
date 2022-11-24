from discord.ext import commands, tasks
from discord.ui import Button, View
from discord import app_commands, utils
from lib.bot import config, MOCBOT, DEV_GUILD, MOC_DB
from typing import Literal, Union, Optional
from datetime import datetime, timedelta
from pytz import timezone
import logging
import discord
import uuid
import re
import asyncio

timeRegex = re.compile("(?:(\d{1,5})(h|s|m|d))+?")
timeDict = {"h":3600, "s":1, "m":60, "d":86400}

class ConfirmButtons(View):
    def __init__(self, *, timeout=10):
        super().__init__(timeout=timeout)
        self.confirmed = None

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

    @discord.ui.button(label="Yes",style=discord.ButtonStyle.green)
    async def accept_button(self, interaction:discord.Interaction, button: Button):
        self.confirmed = True
        self.clear_items()
        await interaction.response.edit_message(view=self)
        self.stop()     

class UserModeration(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.punishments = {}
        self.checkUnmute.start()

    async def convert(self, interaction, arguments):
        args = arguments.lower()
        matches = re.findall(timeRegex, args)
        time = 0
        for value, key in matches:
            try:
                time += timeDict[key] * float(value)
            except:
                pass
        return time

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")
        await self.updatePunishmentDict()

    async def cog_unload(self):
        self.checkUnmute.stop()
        

    @app_commands.command(name="kick", description="Kicks specified user.")
    # @app_commands.guilds(DEV_GUILD)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.describe(
        member="The member you would like to kick.",
        reason="The reason for kicking this user."
    )
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        try:
            await member.send(embed=self.bot.create_embed("MOCBOT MODERATION", f'You have been kicked from the **{interaction.guild.name}** server. {f"REASON: {reason}" if reason else "No reason was specified."}', None))
        except Exception:
            pass
        await interaction.guild.kick(member, reason=f"[{interaction.user}] {reason}")
        await interaction.response.send_message(f'**{member.mention}** has been kicked.', ephemeral=True)

    @app_commands.command(name="ban", description="Bans specified user permanently.")
    # @app_commands.guilds(DEV_GUILD)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.describe(
        user="The user you would like to ban.",
        reason="The reason for banning this user."
    )
    async def ban(self, interaction: discord.Interaction, user: discord.User, reason: str):
        view = ConfirmButtons()
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MODERATION", f"Are you sure you'd like to ban {user.mention}{f' for {reason}?' if reason else '?'}", 0xFFA500), ephemeral=True, view=view)
        view.message = await interaction.original_response()
        await view.wait()
        if view.confirmed:
            try:
                await user.send(embed=self.bot.create_embed("MOCBOT MODERATION", f'You have been banned **permanently** from the **{interaction.guild.name}** server.', None))
            except discord.Forbidden:
                pass
            await interaction.guild.ban(user, reason=f"[{interaction.user}] {reason}")
            await interaction.followup.send(content=f'**{user.mention}** has been banned permanently.', ephemeral=True)

    @app_commands.command(name="unban", description="Unbans specified user.")
    # @app_commands.guilds(DEV_GUILD)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.describe(
        user="The user you would like to unban.",
        reason="The reason for unbanning this user."
    )
    async def unban(self, interaction: discord.Interaction, user: discord.User, reason: str):
        try:
            await interaction.guild.unban(user, reason=f"[{interaction.user}] {reason}")
        except discord.NotFound:
            await interaction.response.send_message(f"The user {user.mention} could not be found in the ban list.", ephemeral=True)
        else:
            await interaction.response.send_message(f"The user {user.mention} could has been unbanned.", ephemeral=True)


    @app_commands.command(name="warnings", description="Check user warnings.")
    # @app_commands.guilds(DEV_GUILD)
    async def warnings(self, interaction: discord.Interaction):
        view=View()
        view.add_item(discord.ui.Button(label="View account",style=discord.ButtonStyle.link,url=f"https://mocbot.masterofcubesau.com/{interaction.guild.id}/account"))
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT WARNINGS", f"You can view all your warnings on your account page.", None), ephemeral=True, view=view)

    WarnGroup = app_commands.Group(name="warn", description="Manages user warnings.")
    # @app_commands.guilds(DEV_GUILD)
    
    @WarnGroup.command(name="add", description="Adds a warning to a user.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        user="The user you would like to warn.",
        reason="The reason for warning this user."
    )
    async def add(self, interaction: discord.Interaction, user: discord.User, reason: str):
        view=View()
        view.add_item(discord.ui.Button(label="View account",style=discord.ButtonStyle.link,url=f"https://mocbot.masterofcubesau.com/{interaction.guild.id}/account"))
        MOC_DB.execute("INSERT INTO Warnings (WarningID, UserID, GuildID, Reason, AdminID) VALUES (%s, %s, %s, %s, %s)", str(uuid.uuid4()), user.id, interaction.guild.id, reason, interaction.user.id)
        await user.send(embed=self.bot.create_embed("MOCBOT WARNINGS", f"You have been warned in **{interaction.guild}** by {interaction.user.mention} for **{reason}**. Please refer to your MOCBOT account to view your warnings.", None), view=view)
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT WARNINGS", f"{user.mention} has successfully been warned for **{reason}**.", None), ephemeral=True)

    @app_commands.command(name="mute", description="Mutes the specified user in voice channels.")
    @app_commands.guilds(DEV_GUILD)
    @app_commands.checks.has_permissions(mute_members=True)
    @app_commands.describe(
        member="The member you would like to mute.",
        reason="The reason for muting this user.",
        time="How long to mute the user for. E.g. 10s, 5m, 3h, 1d"
    )
    async def mute(self, interaction: discord.Interaction, member: discord.Member, reason: str, time: str):
        convertedTime = await self.convert(interaction, time)
        if convertedTime == 0:
            return await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MODERATION", f"The specified time is invalid. Examples: `10s` | `5m` | `4h` | `1d`.", None), ephemeral=True)

        currentTime = utils.utcnow()
        finishTime = currentTime + timedelta(seconds=convertedTime)
        punishmentId = str(uuid.uuid4())
        MOC_DB.execute("INSERT INTO Punishments (PunishmentID, UserID, GuildID, Reason, Time, AdminID) VALUES (%s, %s, %s, %s, %s, %s)", punishmentId, member.id, interaction.guild.id, reason, finishTime.isoformat(), interaction.user.id)
        self.punishments[punishmentId] = finishTime
        await member.edit(mute=True)
        try:
            await member.send(embed=self.bot.create_embed("MOCBOT MODERATION", f'You have been muted in the **{interaction.guild.name}** server for **{reason}**. Time at which you will be unmuted: <t:{round(finishTime.timestamp())}:R>', None))
        except Exception:
            pass
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MODERATION", f'**{member.mention}** has been muted in the **{interaction.guild.name}** server for **{reason}**. The user will automatically be unmuted <t:{round(finishTime.timestamp())}:R>', None), ephemeral=True)

    @tasks.loop(seconds=1.0)
    async def checkUnmute(self):
        for punishmentId in self.punishments:
            if self.punishments[punishmentId] <= utils.utcnow():
                punishmentRes = MOC_DB.record("SELECT * FROM Punishments WHERE PunishmentID = %s", punishmentId)
                if punishmentRes is not None:
                    guild = self.bot.get_guild(punishmentRes[2])
                    member = guild.get_member(punishmentRes[1])
                    await member.edit(mute=False)
                    MOC_DB.execute("DELETE FROM Punishments WHERE PunishmentID = %s", punishmentId)
                    await self.updatePunishmentDict()

    async def updatePunishmentDict(self):
        self.punishments = {punishment[0]: timezone('UTC').localize(punishment[4]) for punishment in MOC_DB.records("SELECT * FROM Punishments")}
        
async def setup(bot):
    await bot.add_cog(UserModeration(bot))