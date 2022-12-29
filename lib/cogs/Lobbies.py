from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput
from discord import app_commands, Interaction, NotFound, PermissionOverwrite, Status
import discord
import logging
import asyncio

class LobbyPrompt(View):
    def __init__(self, *, timeout=180, interaction: discord.Interaction):
        super().__init__(timeout=timeout)
        self.lobby_category = interaction.client.get_channel(MOC_DB.field("SELECT LOBBY_CATEGORY FROM Guild_Settings WHERE GuildID = %s", interaction.guild.id))
        self.interaction = interaction
        self.updateOptions()


    async def on_timeout(self) -> None:
        await self.interaction.delete_original_response()

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user and interaction.user.id == self.interaction.user.id

    def getEmbed(self):
        if LobbyPrompt.is_lobby_leader(self.interaction.user):
            lobby_data = LobbyPrompt.get_lobby_details(self.interaction.user)
            if MOC_DB.column('SELECT UserID FROM LobbyUsers WHERE LobbyName = %s AND GuildID = %s', lobby_data[1], self.interaction.guild.id):
                embed = self.interaction.client.create_embed("MOCBOT LOBBIES", f"It appears you are the lobby leader for **{lobby_data[1]}**", None)
                embed.add_field(name="MEMBERS:", value='\n'.join([self.interaction.guild.get_member(x).mention for x in MOC_DB.column('SELECT UserID FROM LobbyUsers WHERE LobbyName = %s AND GuildID = %s', lobby_data[1], self.interaction.guild.id)]), inline=True)
            else:
                embed = self.interaction.client.create_embed("MOCBOT LOBBIES", f"It appears you are the lobby leader for **{lobby_data[1]}**\nYour lobby is currently empty. Invite people with the button below", None)
        else:
            embed = self.interaction.client.create_embed("MOCBOT LOBBIES", "MOCBOT lobbies allows users to create their own private parties. Create a lobby to enjoy private sessions!", None)
        return embed

    async def invite_user(self, member, lobby):
        lobby_data = LobbyPrompt.get_lobby_details(self.interaction.user)
        await member.add_roles(member.guild.get_role(lobby_data[4]), reason=f"{member} added to {lobby}")
        embed = self.interaction.client.create_embed("MOCBOT LOBBIES", f"You have been invited to join **{lobby}**", None)
        embed.add_field(name="LEADER:", value=f"{member.guild.get_member(lobby_data[5]).mention}", inline=True)
        if MOC_DB.column('SELECT UserID FROM LobbyUsers WHERE LobbyName = %s AND GuildID = %s', lobby, member.guild.id):
            embed.add_field(name="CURRENT USERS:", value='\n'.join([member.guild.get_member(x).mention for x in MOC_DB.column('SELECT UserID FROM LobbyUsers WHERE LobbyName = %s AND GuildID = %s', lobby, member.guild.id)]), inline=True)
        await member.send(embed=embed, view=View().add_item(discord.ui.Button(label="Join lobby",style=discord.ButtonStyle.link, url=str(await member.guild.get_channel(lobby_data[2]).create_invite(reason=f"{member} invited to {lobby}")))))
        MOC_DB.execute("INSERT INTO LobbyUsers (UserID, GuildID, LobbyName) VALUES (%s, %s, %s)", member.id, member.guild.id, lobby)
    
    async def remove_user(self, member, lobby):
        lobby_data = LobbyPrompt.get_lobby_details(self.interaction.user)
        await member.remove_roles(member.guild.get_role(lobby_data[4]), reason=f"{member} kicked from {lobby}")
        MOC_DB.execute("DELETE FROM LobbyUsers WHERE GuildID = %s AND UserID = %s AND LobbyName = %s", member.guild.id, member.id, lobby)

    async def create_lobby(self, name, leader):
        lobby_role = await leader.guild.create_role(name=name, reason=f"{leader} created a lobby.")
        vc_perms = {lobby_role: PermissionOverwrite(speak=True,connect=True,view_channel=True), leader.guild.default_role: PermissionOverwrite(view_channel=True, connect=False)}
        text_perms = {lobby_role: PermissionOverwrite(read_messages=True, send_messages=True), leader.guild.default_role: PermissionOverwrite(read_messages=False)}
        voice_channel = await leader.guild.create_voice_channel(name=name, overwrites=vc_perms, category=self.lobby_category, reason=f"{leader} created a lobby.")
        text_channel = await leader.guild.create_text_channel(name=name, overwrites=text_perms, category=self.lobby_category, reason=f"{leader} created a lobby.")
        await leader.add_roles(lobby_role, reason=f"{leader} added to {name}")
        MOC_DB.execute("INSERT INTO Lobbies (GuildID, LobbyName, VC_ID, TC_ID, RoleID, LeaderID, Invite_Only) VALUES (%s, %s, %s, %s, %s, %s, %s)", leader.guild.id, name, voice_channel.id, text_channel.id, lobby_role.id, leader.id, 0)
    
    async def delete_lobby(self, leader):
        lobby_details = LobbyPrompt.get_lobby_details(leader)
        await self.interaction.client.get_channel(lobby_details[2]).delete(reason=f"{leader} deleted {lobby_details[1]}")
        await self.interaction.client.get_channel(lobby_details[3]).delete(reason=f"{leader} deleted {lobby_details[1]}")
        await leader.guild.get_role(lobby_details[4]).delete(reason=f"{leader} deleted {lobby_details[1]}")
        MOC_DB.execute("DELETE FROM Lobbies WHERE GuildID = %s AND LeaderID = %s", leader.guild.id, leader.id)
        MOC_DB.execute("DELETE FROM LobbyUsers WHERE GuildID = %s AND LobbyName = %s", leader.guild.id, lobby_details[1])


    async def rename_lobby(self, leader, new_name):
        lobby_details = LobbyPrompt.get_lobby_details(leader)
        lobby_role = leader.guild.get_role(lobby_details[4])
        vc_perms = {lobby_role: PermissionOverwrite(speak=True,connect=True,view_channel=True), leader.guild.default_role: PermissionOverwrite(view_channel=True, connect=False)}
        text_perms = {lobby_role: PermissionOverwrite(read_messages=True, send_messages=True), leader.guild.default_role: PermissionOverwrite(read_messages=False)}
        await self.interaction.client.get_channel(lobby_details[2]).edit(name=new_name, overwrites=vc_perms, reason=f"{leader} renamed {lobby_details[1]} to {new_name}")
        await self.interaction.client.get_channel(lobby_details[3]).edit(name=new_name, overwrites=text_perms, reason=f"{leader} renamed {lobby_details[1]} to {new_name}")
        await leader.guild.get_role(lobby_details[4]).edit(name=new_name, reason=f"{leader} renamed {lobby_details[1]} to {new_name}")
        MOC_DB.execute("UPDATE Lobbies SET LobbyName = %s WHERE GuildID = %s AND LeaderID = %s", new_name, leader.guild.id, leader.id)
        MOC_DB.execute("UPDATE LobbyUsers SET LobbyName = %s WHERE GuildID = %s AND LobbyName = %s", new_name, leader.guild.id, lobby_details[1])
    
    async def transfer_lobby(self, new_leader):
        lobby_details = LobbyPrompt.get_lobby_details(self.interaction.user)
        await new_leader.add_roles(new_leader.guild.get_role(lobby_details[4]), reason=f"{new_leader} became leader of {lobby_details[1]}")
        if LobbyPrompt.is_lobby_user(new_leader, lobby_details[1]):
            MOC_DB.execute("DELETE FROM LobbyUsers WHERE GuildID = %s AND UserID = %s", lobby_details[0], new_leader.id)
        MOC_DB.execute("INSERT INTO LobbyUsers (UserID, GuildID, LobbyName) VALUES (%s, %s, %s)", lobby_details[5], lobby_details[0], lobby_details[1])
        MOC_DB.execute("UPDATE Lobbies SET LeaderID = %s WHERE GuildID = %s AND LobbyName = %s", new_leader.id, lobby_details[0], lobby_details[1])
    
    async def setInviteOnly(self, member, value):
        lobby_details = LobbyPrompt.get_lobby_details(member)
        lobby_channel = self.interaction.client.get_channel(lobby_details[2])
        MOC_DB.execute("UPDATE Lobbies SET Invite_Only = %s WHERE GuildID = %s AND LeaderID = %s", value, member.guild.id, member.id)
        if value:
            overwrites = {
                member.guild.get_role(MOC_DB.field("SELECT RoleID FROM Lobbies WHERE GuildID = %s AND LeaderID = %s", member.guild.id, member.id)): PermissionOverwrite(speak=True, connect=True, view_channel=True),
                member.guild.default_role: PermissionOverwrite(connect=False, view_channel=False)
            }
        else:
            overwrites = {
                member.guild.get_role(MOC_DB.field("SELECT RoleID FROM Lobbies WHERE GuildID = %s AND LeaderID = %s", member.guild.id, member.id)): PermissionOverwrite(speak=True, connect=True, view_channel=True),
                member.guild.default_role: PermissionOverwrite(connect=False, view_channel=True)
            }
        await lobby_channel.edit(overwrites=overwrites)

    def is_lobby_hidden(self, member):
        return MOC_DB.field("SELECT Invite_Only FROM Lobbies WHERE GuildID = %s AND LeaderID = %s", member.guild.id, member.id) == 1

    def is_lobby_leader(member):
        return member.id in MOC_DB.column("SELECT LeaderID FROM Lobbies WHERE GuildID = %s", member.guild.id)
    
    def is_lobby_user(member, lobby=None):
        if lobby:
            return member.id in MOC_DB.column("SELECT UserID FROM LobbyUsers WHERE GuildID = %s AND LobbyName = %s", member.guild.id, lobby)
        else:
            return member.id in MOC_DB.column("SELECT UserID FROM LobbyUsers WHERE GuildID = %s", member.guild.id)

    def get_lobby_details(member):
        if LobbyPrompt.is_lobby_leader(member):
            return MOC_DB.record("SELECT * FROM Lobbies WHERE GuildID = %s AND LeaderID = %s", member.guild.id, member.id)
        else:
            lobby_name = MOC_DB.field("SELECT LobbyName FROM LobbyUsers WHERE GuildID = %s AND UserID = %s", member.guild.id, member.id)
            return MOC_DB.record("SELECT * FROM Lobbies WHERE GuildID = %s AND LobbyName = %s", member.guild.id, lobby_name)

    async def updateView(self):
        await self.interaction.edit_original_response(embed=self.getEmbed(), view=self)

    def updateOptions(self):
        self.clear_items()
        if LobbyPrompt.is_lobby_leader(self.interaction.user):
            self.lobby_leader_prompt()
        elif LobbyPrompt.is_lobby_user(self.interaction.user):
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
        lobby_details = LobbyPrompt.get_lobby_details(interaction.user)
        await self.remove_user(interaction.user, lobby_details[1])
        await self.delete_prompt()
        await interaction.response.send_message(f"You have successfully left **{lobby_details[1]}**" , ephemeral=True)

    async def invite_button_callback(self, interaction:discord.Interaction):
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
            for member in msg.mentions:
                if not LobbyPrompt.is_lobby_leader(member) and not LobbyPrompt.is_lobby_user(member):
                    await self.invite_user(member, LobbyPrompt.get_lobby_details(interaction.user)[1])
            await self.updateView()
            # await interaction.followup.send(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", f"Invited {' '.join([x.mention for x in msg.mentions])}", None), ephemeral=True)

    async def kick_button_callback(self, interaction:discord.Interaction):
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
            lobby_details = LobbyPrompt.get_lobby_details(interaction.user)
            for member in msg.mentions:
                await self.remove_user(member, lobby_details[1])
                await member.send(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", f"You have been kicked from **{lobby_details[1]}**", None))
            await self.updateView()
            # await interaction.followup.send(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", f"Kicked {' '.join([x.mention for x in msg.mentions])}", None), ephemeral=True)

    async def transfer_button_callback(self, interaction:discord.Interaction):
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
                if not LobbyPrompt.is_lobby_leader(msg.mentions[0]):
                    lobby_details = LobbyPrompt.get_lobby_details(interaction.user)
                    await self.transfer_lobby(msg.mentions[0])
                    await msg.mentions[0].send(embed=self.interaction.client.create_embed("MOCBOT LOBBIES", f"**{interaction.user}** has transferred their lobby **{lobby_details[1]}** to you.", None))
                    await interaction.followup.send(f"Your lobby has successfully been transferred to **{msg.mentions[0]}**.", ephemeral=True)
                else:
                    await interaction.followup.send(f"The user you have mentioned is currently a leader of another lobby. You may only transfer your lobby to a user of your own lobby or a user who is not a lobby leader.", ephemeral=True)

    async def rename_button_callback(self, interaction:discord.Interaction):
        await interaction.response.send_modal(LobbyRename(self))


    async def delete_button_callback(self, interaction:discord.Interaction):
        await self.delete_lobby(interaction.user)
        await self.delete_prompt()
        await interaction.response.send_message("Your lobby has successfully been deleted.", ephemeral=True)
    
    async def hide_button_callback(self, interaction:discord.Interaction):
        await self.setInviteOnly(interaction.user, 1)
        await self.delete_prompt()
        await interaction.response.send_message("Your lobby is now publicly hidden and is invite only.", ephemeral=True)
    
    async def show_button_callback(self, interaction:discord.Interaction):
        await self.setInviteOnly(interaction.user, 0)
        await self.delete_prompt()
        await interaction.response.send_message("Your lobby is now publicly visible and can be requested to join.", ephemeral=True)



class LobbyCreation(Modal, title='Lobby Creation'):
    lobby_name = TextInput(label='Lobby Name')

    def __init__(self, LobbyPrompt) -> None:
        self.LobbyPrompt = LobbyPrompt
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        # await self.LobbyPrompt.delete_prompt()
        await interaction.response.defer(thinking=False)
        await self.LobbyPrompt.create_lobby(self.lobby_name.value, interaction.user)
        await asyncio.sleep(1)
        self.LobbyPrompt.updateOptions()
        await self.LobbyPrompt.updateView()
        # await interaction.followup.send(embed=self.LobbyPrompt.getEmbed(), view=self.LobbyPrompt)
        # self.LobbyPrompt.interaction = interaction
    
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
            return bool(MOC_DB.field("SELECT LOBBY_CATEGORY FROM Guild_Settings WHERE GuildID = %s", interaction.guild.id))
        return app_commands.check(predicate)

    @tasks.loop(seconds=10)
    async def lobby_offline_detection(self):
        lobbies = MOC_DB.records("SELECT * FROM Lobbies")
        for lobby in lobbies:
            if(guild := self.bot.get_guild(lobby[0])) != None and (old_leader := guild.get_member(lobby[5])) != None:
                if old_leader.status == Status.offline:
                    vc_channel = guild.get_channel(lobby[2])
                    if vc_channel.members:
                        new_lobby_leader = None
                        for member in vc_channel.members:
                            if not member.bot and member.status != Status.offline and member != old_leader:
                                new_lobby_leader = member
                        if new_lobby_leader != None:
                            MOC_DB.execute("DELETE FROM LobbyUsers WHERE GuildID = %s AND UserID = %s", lobby[0], new_lobby_leader.id)
                            MOC_DB.execute("INSERT INTO LobbyUsers (UserID, GuildID, LobbyName) VALUES (%s, %s, %s)", lobby[5], lobby[0], lobby[1])
                            MOC_DB.execute("UPDATE Lobbies SET LeaderID = %s WHERE GuildID = %s AND LobbyName = %s", new_lobby_leader.id, lobby[0], lobby[1])
                            await new_lobby_leader.send(embed=self.bot.create_embed("MOCBOT LOBBIES", f"You are now the lobby leader for **{lobby[1]}** because the original lobby leader went offline.", None), view=View().add_item(discord.ui.Button(label="Join lobby",style=discord.ButtonStyle.link, url=str(await old_leader.guild.get_channel(lobby[2]).create_invite(reason=f"{new_lobby_leader} become leader of {lobby[1]}")))))
                            await old_leader.send(embed=self.bot.create_embed("MOCBOT LOBBIES", f"Your lobby has been transferred to {new_lobby_leader} because you went offline.", None))
                            return
                    await self.bot.get_channel(lobby[2]).delete(reason=f"[AUTO DELETE {lobby[1]}] {old_leader} went offline")
                    await self.bot.get_channel(lobby[3]).delete(reason=f"[AUTO DELETE {lobby[1]}] {old_leader} deleted {lobby[1]}")
                    await guild.get_role(lobby[4]).delete(reason=f"{old_leader} deleted {lobby[1]}")
                    MOC_DB.execute("DELETE FROM Lobbies WHERE GuildID = %s AND LeaderID = %s", guild.id, old_leader.id)
                    MOC_DB.execute("DELETE FROM LobbyUsers WHERE GuildID = %s AND LobbyName = %s", guild.id, lobby[1])
                    await old_leader.send(embed=self.bot.create_embed("MOCBOT LOBBIES", f"Your lobby has been deleted because you went offline.", None))

    @lobby_offline_detection.before_loop
    async def before_lobby_offline_detection(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="lobby", description="Open/manage a MOCBOT lobby.")
    #  @app_commands.guilds(DEV_GUILD)
    @ensure_lobbies()
    async def lobby(self, interaction: discord.Interaction):
        view=LobbyPrompt(timeout=60, interaction=interaction)
        lobby_data = LobbyPrompt.get_lobby_details(interaction.user)
        if LobbyPrompt.is_lobby_leader(interaction.user):
            if MOC_DB.column('SELECT UserID FROM LobbyUsers WHERE LobbyName = %s AND GuildID = %s', lobby_data[1], interaction.guild.id):
                embed = interaction.client.create_embed("MOCBOT LOBBIES", f"It appears you are the lobby leader for **{lobby_data[1]}**", None)
                embed.add_field(name="MEMBERS:", value='\n'.join([interaction.guild.get_member(x).mention for x in MOC_DB.column('SELECT UserID FROM LobbyUsers WHERE LobbyName = %s AND GuildID = %s', lobby_data[1], interaction.guild.id)]), inline=True)
            else:
                embed = interaction.client.create_embed("MOCBOT LOBBIES", f"It appears you are the lobby leader for **{lobby_data[1]}**\nYour lobby is currently empty. Invite people with the button below", None)
        elif LobbyPrompt.is_lobby_user(interaction.user):
            embed = interaction.client.create_embed("MOCBOT LOBBIES", f"It appears you a member of **{lobby_data[1]}**", None)
        else:
            embed = self.bot.create_embed("MOCBOT LOBBIES", "MOCBOT lobbies allows users to create their own private parties. Create a lobby to enjoy private sessions!", None)
        await interaction.response.send_message(embed=embed, view=view)

    @lobby.error
    async def lobby_error(self, interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            view=View()
            view.add_item(discord.ui.Button(label="Configure modules",style=discord.ButtonStyle.link,url=f"https://mocbot.masterofcubesau.com/{interaction.guild.id}/manage"))
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT ERROR", "This server does not have the lobby feature enabled.", 0xFF0000), view=view)

async def setup(bot):
    await bot.add_cog(Lobbies(bot))