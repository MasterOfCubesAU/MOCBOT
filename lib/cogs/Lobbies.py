from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput
from discord import app_commands, Interaction, NotFound, PermissionOverwrite, Status
from requests.exceptions import HTTPError
from lib.bot import DEV_GUILD

from utils.APIHandler import API
import discord
import logging
import asyncio
import traceback
class LobbyPrompt(View):
    def __init__(self, *, timeout=180, interaction: discord.Interaction):
        super().__init__(timeout=timeout)
        settings = API.get(f'/settings/{interaction.guild.id}')
        self.lobby_category = interaction.guild.get_channel(int(settings.get("LobbyCategory") if settings is not None else None))
        self.interaction = interaction
        self.updateOptions()

    async def on_timeout(self) -> None:
        await self.interaction.delete_original_response()

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user and interaction.user.id == self.interaction.user.id

    def getEmbed(self):
        lobby_data = LobbyPrompt.get_lobby_details(self.interaction.user)
        if LobbyPrompt.is_lobby_leader(self.interaction.user, lobby_data):
            lobby_users = API.get(f'/lobby/{self.interaction.guild.id}/{self.interaction.user.id}/users')
            if lobby_users:
                embed = self.interaction.client.create_embed("MOCBOT LOBBIES", f"It appears you are the lobby leader for **{lobby_data.get('LobbyName')}**", None)
                embed.add_field(name="MEMBERS:", value='\n'.join([self.interaction.guild.get_member(int(x)).mention for x in lobby_users]), inline=True)
            else:
                embed = self.interaction.client.create_embed("MOCBOT LOBBIES", f"It appears you are the lobby leader for **{lobby_data.get('LobbyName')}**\nYour lobby is currently empty. Invite people with the button below.", None)
        else:
            embed = self.interaction.client.create_embed("MOCBOT LOBBIES", "MOCBOT lobbies allows users to create their own private parties. Create a lobby to enjoy private sessions!", None)
        return embed

    async def invite_user(self, member, lobby_data, lobby_users):
        await member.add_roles(member.guild.get_role(lobby_data.get("RoleID")), reason=f"{member} added to {lobby_data.get('LobbyName')}")
        embed = self.interaction.client.create_embed("MOCBOT LOBBIES", f"You have been invited to join **{lobby_data.get('LobbyName')}**", None)
        embed.add_field(name="LEADER:", value=f'{member.guild.get_member(lobby_data.get("LeaderID")).mention}', inline=True)
        if lobby_users:
            embed.add_field(name="CURRENT USERS:", value='\n'.join([member.guild.get_member(int(x)).mention for x in lobby_users]), inline=True)
        await member.send(embed=embed, view=View().add_item(discord.ui.Button(label="Join lobby",style=discord.ButtonStyle.link, url=str(await member.guild.get_channel(lobby_data.get("VoiceChannelID")).create_invite(reason=f"{member} invited to {lobby_data.get('LobbyName')}")))))
    
    async def remove_user(self, member, lobby_data):
        await member.remove_roles(member.guild.get_role(lobby_data.get("RoleID")), reason=f"{member} kicked from {lobby_data.get('LobbyName')}")
        await member.send(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", f"You have been kicked from **{lobby_data.get('LobbyName')}**", None))
        API.delete(f'/lobby/{member.guild.id}/{lobby_data.get("LeaderID")}/{member.id}')

    async def create_lobby(self, name, leader):
        lobby_role = await leader.guild.create_role(name=name, reason=f"{leader} created a lobby.")
        vc_perms = {lobby_role: PermissionOverwrite(speak=True,connect=True,view_channel=True), leader.guild.default_role: PermissionOverwrite(view_channel=True, connect=False)}
        text_perms = {lobby_role: PermissionOverwrite(read_messages=True, send_messages=True), leader.guild.default_role: PermissionOverwrite(read_messages=False)}
        voice_channel = await leader.guild.create_voice_channel(name=name, overwrites=vc_perms, category=self.lobby_category, reason=f"{leader} created a lobby.")
        text_channel = await leader.guild.create_text_channel(name=name, overwrites=text_perms, category=self.lobby_category, reason=f"{leader} created a lobby.")
        await leader.add_roles(lobby_role, reason=f"{leader} added to {name}")
        API.post(f'/lobby/{leader.guild.id}', {"LobbyName": name, "VoiceChannelID": str(voice_channel.id), "TextChannelID": str(text_channel.id), "RoleID": str(lobby_role.id), "LeaderID": str(leader.id), "InviteOnly": False})
    
    async def delete_lobby(self, leader):
        lobby_details = LobbyPrompt.get_lobby_details(leader)
        await self.interaction.client.get_channel(lobby_details.get("VoiceChannelID")).delete(reason=f"{leader} deleted {lobby_details.get('LobbyName')}")
        await self.interaction.client.get_channel(lobby_details.get("TextChannelID")).delete(reason=f"{leader} deleted {lobby_details.get('LobbyName')}")
        await leader.guild.get_role(lobby_details.get("RoleID")).delete(reason=f"{leader} deleted {lobby_details.get('LobbyName')}")
        API.delete(f'/lobby/{leader.guild.id}/{leader.id}')

    async def rename_lobby(self, leader, new_name):
        lobby_details = LobbyPrompt.get_lobby_details(leader)
        lobby_role = leader.guild.get_role(lobby_details.get("RoleID"))
        vc_perms = {lobby_role: PermissionOverwrite(speak=True,connect=True,view_channel=True), leader.guild.default_role: PermissionOverwrite(view_channel=True, connect=False)}
        text_perms = {lobby_role: PermissionOverwrite(read_messages=True, send_messages=True), leader.guild.default_role: PermissionOverwrite(read_messages=False)}
        await self.interaction.client.get_channel(lobby_details.get("VoiceChannelID")).edit(name=new_name, overwrites=vc_perms, reason=f"{leader} renamed {lobby_details.get('LobbyName')} to {new_name}")
        await self.interaction.client.get_channel(lobby_details.get("TextChannelID")).edit(name=new_name, overwrites=text_perms, reason=f"{leader} renamed {lobby_details.get('LobbyName')} to {new_name}")
        await leader.guild.get_role(lobby_details.get("RoleID")).edit(name=new_name, reason=f"{leader} renamed {lobby_details.get('LobbyName')} to {new_name}")
        API.patch(f'/lobby/{leader.guild.id}/{leader.id}', {"LobbyName": new_name})
    
    async def transfer_lobby(self, new_leader, lobby_details):
        await new_leader.add_roles(new_leader.guild.get_role(lobby_details.get("RoleID")), reason=f"{new_leader} became leader of {lobby_details.get('LobbyName')}")
        route = f'/lobby/{new_leader.guild.id}/{lobby_details.get("LeaderID")}/users'
        lobby_users = API.get(f'/lobby/{self.interaction.guild.id}/{lobby_details.get("LeaderID")}/users')
        if LobbyPrompt.is_lobby_user(new_leader, lobby_details, lobby_users):
            API.delete(f'/lobby/{new_leader.guild.id}/{lobby_details.get("LeaderID")}/{new_leader.id}')
        API.post(route, [str(lobby_details.get("LeaderID"))])
        API.patch(f'/lobby/{new_leader.guild.id}/{lobby_details.get("LeaderID")}', {"LeaderID": str(new_leader.id)})
    
    async def setInviteOnly(self, member, value):
        lobby_details = LobbyPrompt.get_lobby_details(member)
        lobby_channel = self.interaction.client.get_channel(lobby_details.get("VoiceChannelID"))
        API.patch(f'/lobby/{member.guild.id}/{member.id}', {"InviteOnly": value})
        if value:
            overwrites = {
                member.guild.get_role(lobby_details.get("RoleID")): PermissionOverwrite(speak=True, connect=True, view_channel=True),
                member.guild.default_role: PermissionOverwrite(connect=False, view_channel=False)
            }
        else:
            overwrites = {
                member.guild.get_role(lobby_details.get("RoleID")): PermissionOverwrite(speak=True, connect=True, view_channel=True),
                member.guild.default_role: PermissionOverwrite(connect=False, view_channel=True)
            }
        await lobby_channel.edit(overwrites=overwrites)

    def is_lobby_hidden(self, member):
        lobby_data = API.get(f'/lobby/{member.guild.id}/{member.id}')
        return lobby_data.get("InviteOnly") == 1

    def is_lobby_leader(member, data=None):
        lobby_data = data or LobbyPrompt.get_lobby_details(member)
        return bool(lobby_data.get("LeaderID") == member.id)
    
    def is_lobby_user(member, lobby_details, lobby_users=None):
        lobby_users = lobby_users if lobby_users != None else API.get(f'/lobby/{member.guild.id}/{lobby_details.get("LeaderID")}/users')
        return str(member.id) in lobby_users

    def get_lobby_details(member):
        data = None
        try:
            data = API.get(f"/lobby/{member.guild.id}/{member.id}")
        except HTTPError as e:
            if e.response.status_code == 404:
                try: 
                    data = API.get(f"/lobbies/{member.guild.id}/{member.id}")
                except HTTPError as e:
                    if e.response.status_code == 404:
                        pass 
                    else: 
                        raise e 
                return {} if data is None else data
        else:
            return data

    async def updateView(self, embed=None):
        await self.interaction.edit_original_response(embed=embed or self.getEmbed(), view=self)

    def updateOptions(self):
        self.clear_items()
        lobby_data = LobbyPrompt.get_lobby_details(self.interaction.user)

        if lobby_data != {}:
            if LobbyPrompt.is_lobby_leader(self.interaction.user, lobby_data):
                self.lobby_leader_prompt()
            elif LobbyPrompt.is_lobby_user(self.interaction.user, lobby_data):
                self.lobby_user_prompt()
        else:
            self.new_lobby_prompt()

    def new_lobby_prompt(self):
        create_button = Button(label="Create Lobby", style=discord.ButtonStyle.green, row=1)
        create_button.callback = self.create_button_callback
        self.add_item(create_button)

        close_button = Button(label="Close Menu", style=discord.ButtonStyle.grey, row=1)
        close_button.callback = self.close_menu
        self.add_item(close_button)
    
    def lobby_user_prompt(self):
        leave_button = Button(label="Leave Lobby", style=discord.ButtonStyle.red, row=1)
        leave_button.callback = self.leave_button_callback
        self.add_item(leave_button)

        close_button = Button(label="Close Menu", style=discord.ButtonStyle.grey, row=1)
        close_button.callback = self.close_menu
        self.add_item(close_button)

    def lobby_leader_prompt(self):
        invite_button = Button(label="Invite Users",style=discord.ButtonStyle.grey, row=0, disabled=False)
        invite_button.callback = self.invite_button_callback
        self.add_item(invite_button)
        
        kick_button = Button(label="Kick Users",style=discord.ButtonStyle.grey, row=0, disabled=False)
        kick_button.callback = self.kick_button_callback
        self.add_item(kick_button)

        if self.is_lobby_hidden(self.interaction.user):
            show_button = Button(label="Show Lobby",style=discord.ButtonStyle.grey, row=0, disabled=False)
            show_button.callback = self.show_button_callback
            self.add_item(show_button)
        else:
            hide_button = Button(label="Hide Lobby",style=discord.ButtonStyle.grey, row=0, disabled=False)
            hide_button.callback = self.hide_button_callback
            self.add_item(hide_button)

        transfer_button = Button(label="Transfer Lobby",style=discord.ButtonStyle.grey, row=0, disabled=False)
        transfer_button.callback = self.transfer_button_callback
        self.add_item(transfer_button)

        rename_button = Button(label="Rename Lobby",style=discord.ButtonStyle.grey, row=1)
        rename_button.callback = self.rename_button_callback
        self.add_item(rename_button)

        delete_button = Button(label="Delete Lobby",style=discord.ButtonStyle.red, row=1)
        delete_button.callback = self.delete_button_callback
        self.add_item(delete_button)

        close_button = Button(label="Close Menu", style=discord.ButtonStyle.blurple, row=1)
        close_button.callback = self.close_menu
        self.add_item(close_button)

    async def check_lobby_exists(self, interaction):
        lobby_details = LobbyPrompt.get_lobby_details(interaction.user)
        if lobby_details == {}:
            await self.delete_prompt()
            await interaction.response.send_message(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", f"This lobby does not exist anymore.", None), ephemeral=True)
        return lobby_details
            
    async def delete_prompt(self):
        try:
            await self.interaction.delete_original_response()
        except NotFound:
            await self.interaction.message.delete()
    
    async def close_menu(self, interaction:discord.Interaction):
        await self.delete_prompt()

    async def create_button_callback(self, interaction:discord.Interaction):
        await interaction.response.send_modal(LobbyCreation(self))
    
    async def leave_button_callback(self, interaction:discord.Interaction):
        lobby_details = await self.check_lobby_exists(interaction)
        if lobby_details == {}:
            return
        await self.remove_user(interaction.user, lobby_details)
        await self.delete_prompt()
        await interaction.response.send_message(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", f"You have successfully left {lobby_details.get('LobbyName')}", None), ephemeral=True)

    async def invite_button_callback(self, interaction:discord.Interaction):
        lobby_details = await self.check_lobby_exists(interaction)
        if lobby_details == {}:
            return
        await interaction.response.send_message(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", f"To invite users into your lobby, mention the users you'd like to invite below.", None))
        prompt = await interaction.original_response()
        
        def check(message):
            return (message.author == interaction.user and message.channel == interaction.channel)

        try:
            msg = await self.interaction.client.wait_for("message", check=check, timeout=60)
        except asyncio.TimeoutError:
            await prompt.delete()
        else:
            await msg.delete()
            await prompt.delete()
            lobby_users = API.get(f'/lobby/{self.interaction.guild.id}/{lobby_details.get("LeaderID")}/users')
            members_to_add = []
            await self.updateView(self.interaction.client.create_embed("MOCBOT LOBBIES", f"It appears you are the lobby leader for **{lobby_details.get('LobbyName')}**.\n\n **MEMBERS:**\nInviting Users...", None))
            for member in set(msg.mentions):
                if not LobbyPrompt.is_lobby_leader(member, lobby_details) and not LobbyPrompt.is_lobby_user(member, lobby_details, lobby_users):
                    try:    
                        await self.invite_user(member, lobby_details, lobby_users)
                    except (discord.errors.HTTPException, AttributeError):
                        pass
                    else:
                        members_to_add.append(str(member.id))
            if len(members_to_add) != 0:
                API.post(f'/lobby/{self.interaction.guild.id}/{lobby_details.get("LeaderID")}/users', members_to_add)
            await self.updateView()

    async def kick_button_callback(self, interaction:discord.Interaction):
        lobby_details = await self.check_lobby_exists(interaction)
        if lobby_details == {}:
            return
        await interaction.response.send_message(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", f"To kick users from your lobby, mention the users you'd like to kick below.", None))
        prompt = await interaction.original_response()
        
        def check(message):
            return (message.author == interaction.user and message.channel == interaction.channel)

        try:
            msg = await self.interaction.client.wait_for("message", check=check, timeout=60)
        except asyncio.TimeoutError:
            await prompt.delete()
        else:
            await msg.delete()
            await prompt.delete()
            lobby_users = API.get(f'/lobby/{self.interaction.guild.id}/{lobby_details.get("LeaderID")}/users')
            await self.updateView(self.interaction.client.create_embed("MOCBOT LOBBIES", f"It appears you are the lobby leader for **{lobby_details.get('LobbyName')}**.\n\n **MEMBERS:**\nRemoving Users...", None))
            for member in msg.mentions:
                if (not LobbyPrompt.is_lobby_user(member, lobby_details, lobby_users)) or LobbyPrompt.is_lobby_leader(member, lobby_details):
                    pass
                try:
                    await self.remove_user(member, lobby_details)
                except (discord.errors.HTTPException, AttributeError):
                    pass 
            await self.updateView()

    async def transfer_button_callback(self, interaction:discord.Interaction):
        lobby_details = await self.check_lobby_exists(interaction)
        if lobby_details == {}:
            return
        await interaction.response.send_message(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", f"Mention the user you'd like to transfer your lobby to.", None))
        prompt = await interaction.original_response()

        def check(message):
            return (message.author == interaction.user and message.channel == interaction.channel)

        try:
            msg = await self.interaction.client.wait_for("message", check=check, timeout=60)
        except asyncio.TimeoutError:
            await prompt.delete()
        else:
            await msg.delete()
            await prompt.delete()
            if msg.mentions:
                await self.delete_prompt()
                if not LobbyPrompt.is_lobby_leader(msg.mentions[0]) and not msg.mentions[0].bot:
                    await self.transfer_lobby(msg.mentions[0], lobby_details)
                    await msg.mentions[0].send(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", f"**{interaction.user}** has transferred their lobby **{lobby_details.get('LobbyName')}** to you.", None))
                    await interaction.followup.send(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", f"Your lobby has successfully been transferred to **{msg.mentions[0]}**.", None), ephemeral=True)
                else:
                    await interaction.followup.send(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", f"The user you have mentioned is either currently a leader of another lobby, or not a valid user. You may only transfer your lobby to a user of your own lobby or a user who is not a lobby leader.", None), ephemeral=True)

    async def rename_button_callback(self, interaction:discord.Interaction):
        lobby_details = await self.check_lobby_exists(interaction)
        if lobby_details == {}:
            return
        await interaction.response.send_modal(LobbyRename(self))

    async def delete_button_callback(self, interaction:discord.Interaction):
        lobby_details = await self.check_lobby_exists(interaction)
        if lobby_details == {}:
            return
        await interaction.response.defer(thinking=False)
        await self.updateView(self.interaction.client.create_embed("MOCBOT LOBBIES", f"Removing lobby...", None))
        await self.delete_lobby(interaction.user)
        await self.delete_prompt()
        await interaction.followup.send(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", "Your lobby has successfully been deleted.", None), ephemeral=True)
    
    async def hide_button_callback(self, interaction:discord.Interaction):
        lobby_details = await self.check_lobby_exists(interaction)
        if lobby_details == {}:
            return
        await self.setInviteOnly(interaction.user, 1)
        await self.delete_prompt()
        await interaction.response.send_message(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", "Your lobby is now publicly hidden and is invite only.", None), ephemeral=True)
    
    async def show_button_callback(self, interaction:discord.Interaction):
        lobby_details = await self.check_lobby_exists(interaction)
        if lobby_details == {}:
            return
        await self.setInviteOnly(interaction.user, 0)
        await self.delete_prompt()
        await interaction.response.send_message(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", "Your lobby is now publicly visible and can be requested to join.", None), ephemeral=True)

class LobbyCreation(Modal, title='Lobby Creation'):
    lobby_name = TextInput(label='Lobby Name')

    def __init__(self, LobbyPrompt) -> None:
        self.LobbyPrompt = LobbyPrompt
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=False)
        self.LobbyPrompt.clear_items()
        await self.LobbyPrompt.updateView(interaction.client.create_embed("MOCBOT LOBBIES", f"Creating lobby **{self.lobby_name.value}**", None))
        await self.LobbyPrompt.create_lobby(self.lobby_name.value, interaction.user)
        await asyncio.sleep(1)
        self.LobbyPrompt.updateOptions()
        await self.LobbyPrompt.updateView()

class LobbyRename(Modal, title='Rename Lobby'):
    lobby_name = TextInput(label='Lobby Name')

    def __init__(self, LobbyPrompt) -> None:
        self.LobbyPrompt = LobbyPrompt
        self.logger = logging.getLogger(__name__)
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=False)
        await self.LobbyPrompt.rename_lobby(interaction.user, self.lobby_name.value)
        await asyncio.sleep(1)
        self.LobbyPrompt.updateOptions()
        await self.LobbyPrompt.updateView()

class Lobbies(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.lobby_offline_detection.start()
        self.logger = logging.getLogger(__name__)

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")

    def ensure_lobbies():
        def predicate(interaction: discord.Interaction) -> bool:
            settings = API.get(f'/settings/{interaction.guild.id}')
            return bool(settings.get("LobbyCategory", None) if settings is not None else False)
        return app_commands.check(predicate)

    @tasks.loop(seconds=120)
    async def lobby_offline_detection(self):    
        lobbies = API.get('/lobbies/')
        for lobby in lobbies:
            guild = self.bot.get_guild(int(lobby.get("GuildID")))
            if guild == None:
                continue
            old_leader = guild.get_member(int(lobby.get("LeaderID")))
            if old_leader != None:
                if old_leader.status == Status.offline:
                    vc_channel = guild.get_channel(int(lobby.get("VoiceChannelID")))
                    if vc_channel.members:
                        new_lobby_leader = None
                        for member in vc_channel.members:
                            if not member.bot and member.status != Status.offline and member != old_leader:
                                new_lobby_leader = member
                        if new_lobby_leader != None:
                            API.delete(f'/lobby/{lobby.get("GuildID")}/{lobby.get("LeaderID")}/{new_lobby_leader.id}')
                            API.post(f'/lobby/{lobby.get("GuildID")}/{lobby.get("LeaderID")}/users', [str(lobby.get("LeaderID"))])
                            API.patch(f'/lobby/{lobby.get("GuildID")}/{lobby.get("LeaderID")}', {"LeaderID": str(new_lobby_leader.id)})
                            await new_lobby_leader.send(embed=self.bot.create_embed("MOCBOT LOBBIES", f"You are now the lobby leader for **{lobby.get('LobbyName')}** because the original lobby leader went offline.", None), view=None)
                            await old_leader.send(embed=self.bot.create_embed("MOCBOT LOBBIES", f"Your lobby has been transferred to {new_lobby_leader} because you went offline.", None))
                            return
                    await self.bot.get_channel(int(lobby.get("VoiceChannelID"))).delete(reason=f"[AUTO DELETE {lobby.get('LobbyName')}] {old_leader} went offline")
                    await self.bot.get_channel(int(lobby.get("TextChannelID"))).delete(reason=f"[AUTO DELETE {lobby.get('LobbyName')}] {old_leader} deleted {lobby.get('LobbyName')}")
                    await guild.get_role(int(lobby.get("RoleID"))).delete(reason=f"{old_leader} deleted {lobby.get('LobbyName')}")
                    API.delete(f'/lobby/{lobby.get("GuildID")}/{lobby.get("LeaderID")}')
                    await old_leader.send(embed=self.bot.create_embed("MOCBOT LOBBIES", f"Your lobby has been deleted because you went offline.", None))

    @lobby_offline_detection.before_loop
    async def before_lobby_offline_detection(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="lobby", description="Open/manage a MOCBOT lobby.")
    @ensure_lobbies()
    async def lobby(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        guild = self.bot.get_guild(interaction.guild.id)
        user = guild.get_member(interaction.user.id)
        if user.status == Status.offline:
            return await interaction.followup.send(embed=interaction.client.create_embed("MOCBOT LOBBIES", f"It appears that you are offline. Please change your status to any other status before interacting with the Lobby system. Please note that any lobby you create will be deleted if you are offline.", None), ephemeral=True)
        view=LobbyPrompt(timeout=60, interaction=interaction)
        lobby_data = LobbyPrompt.get_lobby_details(interaction.user)
        embed = None
        if lobby_data != {}:
            if LobbyPrompt.is_lobby_leader(interaction.user, lobby_data):
                users = API.get(f'/lobby/{interaction.guild.id}/{lobby_data.get("LeaderID", None)}/users')
                if users:
                    embed = interaction.client.create_embed("MOCBOT LOBBIES", f"It appears you are the lobby leader for **{lobby_data.get('LobbyName', None)}**", None)
                    embed.add_field(name="MEMBERS:", value='\n'.join([interaction.guild.get_member(int(x)).mention for x in users]), inline=True)
                else:
                    embed = interaction.client.create_embed("MOCBOT LOBBIES", f"It appears you are the lobby leader for **{lobby_data.get('LobbyName', None)}**\nYour lobby is currently empty. Invite people with the button below.", None)
            elif LobbyPrompt.is_lobby_user(interaction.user, lobby_data):
                embed = interaction.client.create_embed("MOCBOT LOBBIES", f"It appears you a member of **{lobby_data.get('LobbyName', None)}**", None)
        else:
            embed = self.bot.create_embed("MOCBOT LOBBIES", "MOCBOT lobbies allows users to create their own private parties. Create a lobby to enjoy private sessions!", None)
        await interaction.followup.send(embed=embed, view=view)

    @lobby.error
    async def lobby_error(self, interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            view=View()
            view.add_item(discord.ui.Button(label="Configure modules",style=discord.ButtonStyle.link,url=f"https://mocbot.masterofcubesau.com/{interaction.guild.id}/manage"))
            await interaction.followup.send(embed=self.bot.create_embed("MOCBOT ERROR", "This server does not have the lobby feature enabled.", 0xFF0000), view=view)

async def setup(bot):
    await bot.add_cog(Lobbies(bot))