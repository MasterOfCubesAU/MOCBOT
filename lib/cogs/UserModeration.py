from discord.ext import commands
from discord.ui import Button, View
from discord import app_commands
from utils.APIHandler import API
import logging
import discord


class ConfirmButtons(View):
    def __init__(self, *, timeout=10):
        super().__init__(timeout=timeout)
        self.confirmed = None

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        self.confirmed = True
        self.clear_items()
        await interaction.response.edit_message(view=self)
        self.stop()


class UserModeration(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")

    @app_commands.command(name="kick", description="Kicks specified user.")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.describe(
        member="The member you would like to kick.",
        reason="The reason for kicking this user.",
    )
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ):
        try:
            await member.send(
                embed=self.bot.create_embed(
                    "MOCBOT MODERATION",
                    f"You have been kicked from the **{interaction.guild.name}** server. "
                    f'{f"REASON: {reason}" if reason else "No reason was specified."}',
                    None,
                )
            )
        except Exception:
            pass
        await interaction.guild.kick(member, reason=f"[{interaction.user}] {reason}")
        await interaction.response.send_message(f"**{member.mention}** has been kicked.", ephemeral=True)

    @app_commands.command(name="ban", description="Bans specified user permanently.")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.describe(
        user="The user you would like to ban.",
        reason="The reason for banning this user.",
    )
    async def ban(self, interaction: discord.Interaction, user: discord.User, reason: str):
        view = ConfirmButtons()
        await interaction.response.send_message(
            embed=self.bot.create_embed(
                "MOCBOT MODERATION",
                f"Are you sure you'd like to ban {user.mention}{f' for {reason}?' if reason else '?'}",
                0xFFA500,
            ),
            ephemeral=True,
            view=view,
        )
        view.message = await interaction.original_response()
        await view.wait()
        if view.confirmed:
            try:
                await user.send(
                    embed=self.bot.create_embed(
                        "MOCBOT MODERATION",
                        f"You have been banned **permanently** from the **{interaction.guild.name}** server.",
                        None,
                    )
                )
            except discord.Forbidden:
                pass
            await interaction.guild.ban(user, reason=f"[{interaction.user}] {reason}")
            await interaction.followup.send(
                content=f"**{user.mention}** has been banned permanently.",
                ephemeral=True,
            )

    @app_commands.command(name="unban", description="Unbans specified user.")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.describe(
        user="The user you would like to unban.",
        reason="The reason for unbanning this user.",
    )
    async def unban(self, interaction: discord.Interaction, user: discord.User, reason: str):
        try:
            await interaction.guild.unban(user, reason=f"[{interaction.user}] {reason}")
        except discord.NotFound:
            await interaction.response.send_message(
                f"The user {user.mention} could not be found in the ban list.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"The user {user.mention} could has been unbanned.",
                ephemeral=True,
            )

    @app_commands.command(name="warnings", description="Check user warnings.")
    async def warnings(self, interaction: discord.Interaction):
        view = View()
        view.add_item(
            discord.ui.Button(
                label="View account",
                style=discord.ButtonStyle.link,
                url=f"https://mocbot.masterofcubesau.com/{interaction.guild.id}/account",
            )
        )
        await interaction.response.send_message(
            embed=self.bot.create_embed(
                "MOCBOT WARNINGS",
                "You can view all your warnings on your account page.",
                None,
            ),
            ephemeral=True,
            view=view,
        )

    WarnGroup = app_commands.Group(name="warn", description="Manages user warnings.")

    @WarnGroup.command(name="add", description="Adds a warning to a user.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        user="The user you would like to warn.",
        reason="The reason for warning this user.",
    )
    async def add(self, interaction: discord.Interaction, user: discord.User, reason: str):
        view = View()
        view.add_item(
            discord.ui.Button(
                label="View account",
                style=discord.ButtonStyle.link,
                url=f"https://mocbot.masterofcubesau.com/{interaction.guild.id}/account",
            )
        )
        API.post(
            f"/warnings/{interaction.guild.id}/{user.id}",
            {"reason": reason, "adminID": str(interaction.user.id)},
        )
        await user.send(
            embed=self.bot.create_embed(
                "MOCBOT WARNINGS",
                f"You have been warned in **{interaction.guild}** by {interaction.user.mention} for **{reason}**. "
                "Please refer to your MOCBOT account to view your warnings.",
                None,
            ),
            view=view,
        )
        await interaction.response.send_message(
            embed=self.bot.create_embed(
                "MOCBOT WARNINGS",
                f"{user.mention} has successfully been warned for **{reason}**.",
                None,
            ),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(UserModeration(bot))
