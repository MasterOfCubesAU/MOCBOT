from discord.ext import commands
from discord.ui import Button, View
from discord import app_commands
from lib.bot import config, logger, MOCBOT, DEV_GUILD, MOC_DB
from typing import Literal, Union, Optional
import discord

import asyncio

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


class Commands(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"[COG] Loaded {self.__class__.__name__}")


    @app_commands.command(name="announce", description="Announces a message to a given audience and channel")
  #  @app_commands.guilds(DEV_GUILD)
    @app_commands.checks.has_permissions(administrator=True, manage_guild=True)
    @app_commands.describe(
        audience="The audience group to target.",
        channel="The text channel to target."
    )
    async def announce(self, interaction: discord.Interaction, audience: Literal["none", "here", "everyone"], channel: discord.TextChannel, message: str):
        embed = discord.Embed(description=message, colour=0xDC3145, timestamp=discord.utils.utcnow())
        match audience:
            case "everyone":
                await channel.send("@everyone", embed=embed)
            case "here":
                await channel.send("@here", embed=embed)
            case "none":
                await channel.send(embed=embed)
        await interaction.response.send_message(f"Announcement sent to {channel.mention}", ephemeral=True)

    @app_commands.command(name="purge", description="Remove content from a channel.")
  #  @app_commands.guilds(DEV_GUILD)
    @app_commands.checks.has_permissions(administrator=True, manage_messages=True)
    @app_commands.describe(
        quantity="The amount of messages to purge. Limited to 100.",
        user="The user to purge. Omit for channel purging."
    )
    async def purge(self, interaction: discord.Interaction, quantity: app_commands.Range[int, 1, 100], user: Optional[discord.User]):
        await interaction.response.defer(ephemeral=True, thinking=True)

        async def delete_older_messages(messages):
            for msg in messages:
                await msg.delete()
                await asyncio.sleep(0.75)
        
        async def convert(seconds):
            minutes = (seconds % 3600) // 60
            seconds %= 60
            return_str = ""
            if minutes:
                return_str += f"{int(minutes)}m"
            if seconds:
                return_str += f"{int(seconds)}s"
            return return_str

        to_purge = []
        async for x in interaction.channel.history(limit=None):
            if user and x.author == user:
                to_purge.append(x)
            elif not user:
                to_purge.append(x)
            if len(to_purge) == quantity:
                break
        
        older_messages = [msg for msg in to_purge if (discord.utils.utcnow() - msg.created_at).days >= 14]
        recent_messages = [msg for msg in to_purge if (discord.utils.utcnow() - msg.created_at).days < 14]

        if older_messages:
            view = ConfirmButtons()
            await interaction.followup.send(embed=self.bot.create_embed("MOCBOT PURGE", f"**{len(older_messages)}** message(s) over 14 days old were found. This will take roughly {await convert(0.75 * len(older_messages))} to delete. Are you sure you'd like to continue?", 0xFFA500), ephemeral=True, view=view)
            view.message = await interaction.original_message()
            await view.wait()
            if view.confirmed:
                await delete_older_messages(older_messages)
                await interaction.channel.delete_messages(recent_messages, reason=f"{interaction.user} purged messages")
                await interaction.followup.send(f"**{len(to_purge)}** messages deleted. Channel purge complete.", ephemeral=True)
        else:
            await interaction.channel.delete_messages(recent_messages, reason=f"{interaction.user} purged messages")
            await interaction.followup.send(f"**{len(to_purge)}** messages deleted. Channel purge complete.", ephemeral=True)

    @app_commands.command(name="setup", description="Configure MOCBOT server settings.")
  #  @app_commands.guilds(DEV_GUILD)
    async def setup(self, interaction: discord.Interaction):
        view=View()
        view.add_item(discord.ui.Button(label="Setup",style=discord.ButtonStyle.link,url=f"https://mocbot.masterofcubesau.com/{interaction.guild.id}/manage"))
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT SETUP", f"To ensure full functionality of {self.bot.user.mention}, you must setup the bot to accomodate your server.", None), ephemeral=True, view=view)

    @app_commands.command(name="invite", description="Invite MOCBOT to your server.")
  #  @app_commands.guilds(DEV_GUILD)
    async def invite(self, interaction: discord.Interaction):
        view=View()
        view.add_item(discord.ui.Button(label="Invite MOCBOT",style=discord.ButtonStyle.link,url=f"https://discord.com/api/oauth2/authorize?client_id=417962459811414027&permissions=8&scope=bot%20applications.commands"))
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT SETUP", f"Use the button below to invite MOCBOT into your own server!", None), view=view)

    @app_commands.command(name="contact", description="Contact the MOCBOT team.")
  #  @app_commands.guilds(DEV_GUILD)
    async def contact(self, interaction: discord.Interaction):
        view=View()
        view.add_item(discord.ui.Button(label="Contact us",style=discord.ButtonStyle.link,url=f"https://masterofcubesau.com/contact"))
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT CONTACT", f"Use the button below to contact the team.", None), view=view)

    @app_commands.command(name="help", description="Displays MOCBOT help.")
  #  @app_commands.guilds(DEV_GUILD)
    async def help(self, interaction: discord.Interaction):
        view=View()
        view.add_item(discord.ui.Button(label="Get help",style=discord.ButtonStyle.link,url=f"https://mocbot.masterofcubesau.com/help"))
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT HELP", f"Use the button below to get help using MOCBOT.", None), view=view)

    @app_commands.command(name="dashboard", description="Displays MOCBOT dashboard.")
  #  @app_commands.guilds(DEV_GUILD)
    async def dashboard(self, interaction: discord.Interaction):
        view=View()
        view.add_item(discord.ui.Button(label="View dashboard",style=discord.ButtonStyle.link,url=f"https://mocbot.masterofcubesau.com/dashboard"))
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT HELP", f"Use the button below to access the MOCBOT dashboard.", None), view=view)

    @app_commands.command(name="account", description="Displays your account.")
  #  @app_commands.guilds(DEV_GUILD)
    async def account(self, interaction: discord.Interaction):
        view=View()
        view.add_item(discord.ui.Button(label="View account",style=discord.ButtonStyle.link,url=f"https://mocbot.masterofcubesau.com/{interaction.guild.id}/account"))
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT HELP", f"Use the button below to access your MOCBOT account.", None), view=view)

    @app_commands.command(name="info", description="Displays info for a user/server.")
    @app_commands.describe(
        member="The member to search for."
    )
    async def info(self, interaction: discord.Interaction, member: Optional[discord.Member]):
        target = member or interaction.guild
        if isinstance(target, discord.Member):
            embed_content = f'''
            >>> User: **{target.name}** ({target.id})
            
            **{target.name}** joined **{interaction.guild}** at `{target.joined_at.strftime("%I:%M%p, %d/%m/%Y %Z")}` and created their account at `{target.created_at.strftime("%I:%M%p, %d/%m/%Y %Z")}`
            '''
        else:
            embed_content = f'''
            >>> Server: **{target}** ({target.id})
            
            **{target}** was created at `{target.created_at.strftime("%I:%M%p, %d/%m/%Y %Z")}` and is owned by {target.owner.mention}
            '''
        embed = self.bot.create_embed("MOCBOT PROFILE", f"{embed_content}", None)
        await interaction.response.send_message(embed=embed)



async def setup(bot):
    await bot.add_cog(Commands(bot))