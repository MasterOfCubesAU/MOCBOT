from discord.ext import commands
from discord import app_commands, DMChannel
from utils.APIHandler import API
from requests.exceptions import HTTPError
import discord 
from expiringdict import ExpiringDict

import typing
import asyncio
import logging

class AFK(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.cache = ExpiringDict(max_len=500, max_age_seconds=300, items=None)

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")

    def add_user(self, data: object):
        route = f'/afk/{data["guild_id"]}/{data["user_id"]}'
        newData = API.post(route, {"MessageID": data["msg_id"], "ChannelID": data["channel_id"], "OldName": data["old_name"], "Reason": data["reason"]})
        self.cache[f'{data["guild_id"]}/{data["user_id"]}'] = {key: value for key, value in newData.items() if key not in ["UserID", "GuildID"]}
    
    def remove_user(self, data: object):
        route = f'/afk/{data["guild_id"]}/{data["user_id"]}'
        API.delete(route)
        try:
            del self.cache[f'{data["guild_id"]}/{data["user_id"]}']
        except KeyError:
            pass
    
    def get_user(self, guild_id, user_id):
        data = self.cache.get(f'{guild_id}/{user_id}', None)
        if data is None:
            try:
                data = API.get(f'/afk/{guild_id}/{user_id}')
            except HTTPError as e:
                if e.response.status_code == 404:
                    self.cache[f'{guild_id}/{user_id}'] = {}
            else:
                self.cache[f'{guild_id}/{user_id}'] = data
        return data
    
    async def get_message(self, data):
        channel = self.bot.get_channel(data["ChannelID"])
        return await channel.fetch_message(data["MessageID"])

    @app_commands.command(name="afk", description="Set an AFK status.")
    async def afk(self, interaction: discord.Interaction, reason: typing.Optional[str] = "N/A"):
        route = f'/afk/{interaction.guild.id}/{interaction.user.id}'
        try:
            data = API.get(route)
        except HTTPError as e:
            if e.response.status_code == 404:
                afk_embed = self.bot.create_embed("MOCBOT AFK", f"{interaction.user.mention} is now AFK.", None)
                afk_embed.add_field(name="REASON:", value="{}".format(reason)).set_thumbnail(url=interaction.user.display_avatar.url)
                await interaction.response.send_message(embed=afk_embed)
                msg = await interaction.original_response()
                self.add_user({"msg_id": str(msg.id), "channel_id": str(msg.channel.id), "old_name": interaction.user.display_name, "reason": reason, "user_id": interaction.user.id, "guild_id": interaction.guild.id})
                if interaction.user.id != interaction.guild.owner_id:
                    await interaction.user.edit(nick=f"[AFK] {interaction.user.display_name}", reason="User went AFK")
            else:
                raise e
        else:
            if interaction.user.id != interaction.guild.owner_id:
                await interaction.user.edit(nick=data["OldName"], reason="User removed from AFK")
            try:
                message_to_delete = await self.get_message(data)
                await message_to_delete.delete()
            except discord.errors.NotFound:
                pass
            self.remove_user({"guild_id": interaction.guild.id, "user_id": interaction.user.id})
            afk_embed = self.bot.create_embed("MOCBOT AFK", f"{interaction.user.mention} is now back.", None).set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=afk_embed)
            await asyncio.sleep(5)
            await interaction.delete_original_response()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or isinstance(message.channel, DMChannel):
            return
        data = self.get_user(message.guild.id, message.author.id)  
        if data is not None and data != {}:
            if message.author.id != message.channel.guild.owner_id:
                await message.author.edit(nick=data["OldName"], reason="User removed from AFK")
            try:
                message_to_delete = await self.get_message(data)
            except discord.errors.NotFound:
                pass
            else:
                await message_to_delete.delete()
            self.remove_user({"guild_id": message.guild.id, "user_id": message.author.id})
            afk_embed = self.bot.create_embed("MOCBOT AFK", f"{message.author.mention} is now back.", None)
            afk_embed.set_thumbnail(url=message.author.display_avatar.url)
            return await message.channel.send(embed=afk_embed, delete_after=5)

        if message.mentions and not message.author.bot:
            for id in [x.id for x in message.mentions]:
                data = self.get_user(message.guild.id, id)
                if data is not None and data != {}:
                    user = self.bot.get_user(id)
                    afk_embed = self.bot.create_embed("MOCBOT AFK", f"{user.mention} is currently AFK.", None)
                    afk_embed.add_field(name="REASON:", value="{}".format(data["Reason"])).set_thumbnail(url=user.display_avatar.url)
                    return await message.channel.send(message.author.mention, embed=afk_embed, delete_after=5) 

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel != after.channel:
            data = self.get_user(member.guild.id, member.id)
            if data is not None and data != {}:
                channel = self.bot.get_channel(data["ChannelID"])
                if member.id != channel.guild.owner_id:
                    await member.edit(nick=data["OldName"], reason="User removed from AFK")
                try:
                    message_to_delete = await channel.fetch_message(data["MessageID"])
                except discord.errors.NotFound:
                    pass
                else:
                    await message_to_delete.delete()
                self.remove_user({"guild_id": member.guild.id, "user_id": member.id})
                afk_embed = self.bot.create_embed("MOCBOT AFK", f"{member.mention} is now back.", None)
                afk_embed.set_thumbnail(url=member.display_avatar.url)
                return await channel.send(embed=afk_embed, delete_after=5)
                    
async def setup(bot):
    await bot.add_cog(AFK(bot))
