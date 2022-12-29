from discord.ext import commands, tasks
from discord.ui import View
from discord import app_commands, File, Object, Status
from utils.APIHandler import API
from lib.bot import config, DEV_GUILD
from requests.exceptions import HTTPError

import discord
import logging

from PIL import Image, ImageDraw, ImageFont
import requests
import asyncio
from io import BytesIO
import datetime
import math
import json
from typing import Optional

class Levels(commands.Cog):

    voiceXPInterval = 20 # every x minutes

    def __init__(self, bot):
        self.bot = bot
        self.global_multiplier = 1
        self.messages_xp = 4
        self.voice_xp_rate = 48 # per hour
        self.logger = logging.getLogger(__name__)

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")
        # await self.level_integrity()
        # await self.update_roles()
        self.voice_xp.start()

    async def cog_unload(self):
        self.voice_xp.stop()

    # Helper Functions
    async def get_required_xp(level):
        return (6 * ((level)) ** 2 + 94)
    
    async def calculate_correct_level(self, xp):
        if xp >= 100:
            return int(math.sqrt((xp - 94) / 6))
        else:
            return 0
    
    async def xp_away(self, member):
        data = await self.get_xp_data(member)
        if data is not None:
            required_xp = 6 * ((data.get("Level", None) + 1)) ** 2 + 94
            xp_difference = required_xp - data.get("XP", None)
            return xp_difference

    async def get_xp_data(self, member):
        try:
            data = API.get(f'/xp/{member.guild.id}/{member.id}')
        except HTTPError as e:
            if e.response.status_code == 404:
                return None 
            else:
                raise e
        else:
            return data

    async def get_rank(self, member):
        guild_xp = API.get(f'/xp/{member.guild.id}')
        if not guild_xp:
            return None
        guild_xp.sort(key=lambda user: int(user["XP"]), reverse=True)
        guild_member_ids = list(map(lambda member: member.id, member.guild.members))
        return [id for id in map(lambda user: int(user["UserID"]), guild_xp) if id in guild_member_ids].index(member.id)

    async def add_xp(self, member, amount: int):
        route = f'/xp/{member.guild.id}/{member.id}'
        data = await self.get_xp_data(member)
        xp = data.get("XP", None) if data is not None else None
        if xp is not None:
            if max(xp + amount, 0) != 0:
                API.patch(route, {"XP": xp + amount})
            else:
                API.delete(route)
        else:
            if amount > 0:
                API.post(route, {"XP": amount})

        level_up_required = await self.level_integrity(member)
        # await self.update_roles(member)
        return level_up_required

    async def set_xp(self, member, value: int):
        if value > 0:
            if data := (await self.get_xp_data()) != None:
                current_xp = data.get("XP")
            await self.add_xp(member, value - (current_xp if current_xp is not None else 0))
        else:
            API.delete(f'/xp/{member.guild.id}/{member.id}')
            # await self.update_roles(member)

    async def message_xp(self, message):
        route = f'/xp/{message.guild.id}/{message.author.id}'
        xp_lock = API.get(route).get("XPLock", None)
        if xp_lock:
            if datetime.datetime.now() > datetime.datetime.fromisoformat(str(xp_lock)):
                # TODO: below if condition missing checkLevelUpPerms
                if await self.add_xp(message.author, self.messages_xp * self.global_multiplier):
                    await message.channel.send(message.author.mention, file=await self.generate_level_up_card(message.author))
                API.post(route, {"XPLock": (datetime.datetime.now() + datetime.timedelta(seconds=60)).isoformat()})
        else:
            await self.add_xp(message.author, self.messages_xp * self.global_multiplier)


    @commands.Cog.listener()
    async def on_message(self, message):
        if (
            not message.author.bot
            and not message.interaction
            and message.author.id not in config["DEVELOPERS"]
            and message.guild
        ):
            await self.message_xp(message)

    def keystoint(self, x):
        return {int(k): v for k, v in x.items()}

    # async def checkLevelUpPerms(self, guild_id):
    #     return bool(int(MOC_DB.field(f"SELECT XP_LVL_UP_MSG FROM Guild_Settings WHERE GuildID = {guild_id}")))

    async def level_integrity(self, member=None):
        route = f'/xp/{member.guild.id}/{member.id}'
        data = await self.get_xp_data(member)
        if member and data is not None:
            correct_level = await self.calculate_correct_level(data.get("XP", None))
            current_level = data.get("Level", None)
            if current_level != correct_level:
                API.patch(route, {"Level": correct_level})
                if current_level < correct_level:
                   return True               
        # else:
        #     data = MOC_DB.records("SELECT * FROM XP")
        #     for record in data:
        #         correct_level = await self.calculate_correct_level(record[2])
        #         if record[3] != correct_level:
        #             MOC_DB.execute("UPDATE XP SET Level = %s WHERE UserID = %s AND GuildID = %s", correct_level, record[1], record[0])

    # async def update_roles(self, member=None):
    #     if member:
    #         if (role_map := MOC_DB.field("SELECT LevelRoles FROM Roles WHERE GuildID = %s", member.guild.id)) != None:
    #             role_map = self.keystoint(json.loads(role_map))
    #             member_level = await self.get_level(member) or 0
    #             member_roles = member.roles
    #             low_difference = [
    #                 role_map[x]
    #                 for x in role_map
    #                 if role_map[x] not in [role.id for role in member_roles]
    #                 and x <= member_level
    #             ]
    #             high_difference = [
    #                 role.id
    #                 for role in member_roles
    #                 if role.id in {value: key for key, value in role_map.items()}
    #                 and {value: key for key, value in role_map.items()}[role.id]
    #                 > member_level
    #             ]
    #             if low_difference:
    #                 for x in low_difference:
    #                     await member.add_roles(Object(id=int(x)), reason="Role Adjustment")
    #             if high_difference:
    #                 for x in high_difference:
    #                     await member.remove_roles(Object(id=int(x)), reason="Role Adjustment")
    #     else:
    #         data = MOC_DB.records("SELECT * FROM Roles")
    #         for record in data:
    #             if (guild := self.bot.get_guild(record[0])) != None:
    #                 for member in guild.members:
    #                     await self.update_roles(member)

    async def generate_level_up_card(self, member):
        template = Image.open("./assets/levels/template.jpg")
        raw_avatar = requests.get(member.display_avatar.url, stream=True)
        avatar = Image.open(raw_avatar.raw).convert("RGBA")
        canvas = ImageDraw.Draw(template)
         
        canvas.text((329, 90), str("YOU HAVE "), fill="#ffffff", font=ImageFont.truetype("./assets/fonts/Bebas.ttf", size=75))

        x_offset = ImageFont.truetype("./assets/fonts/Bebas.ttf", size=75).getsize(str("YOU HAVE "))[0]
        canvas.text((329 + x_offset, 90),"LEVELLED UP!",fill="#dc3545",font=ImageFont.truetype("./assets/fonts/Bebas.ttf", size=75))
        canvas.text((329, 179),"LEVEL {}".format(await self.get_level(member)),fill="#dc3545",font=ImageFont.truetype("./assets/fonts/Bebas.ttf", size=50))

        x_offset =  ImageFont.truetype("./assets/fonts/Bebas.ttf", size=50).getsize("LEVEL {}".format(await self.get_level(member)))[0]
        canvas.text((329+ x_offset + 10, 179,),"NEXT LEVEL {} XP AWAY".format(await self.xp_away(member)),fill="rgb(80, 80, 80)",font=ImageFont.truetype("./assets/fonts/Bebas.ttf", size=50))
        
        avatar = avatar.resize((225, 225), 0)
        template.paste(avatar, (60, 40), mask=avatar)
        tempFile = BytesIO()
        template.save(tempFile, format="PNG", optimize=True)
        tempFile.seek(0)
        return File(tempFile, "level_up.png")

    async def generate_rank_card(self, member):
        XP_DATA = await self.get_xp_data(member)

        template = Image.open("./assets/levels/template.jpg")
        raw_avatar = requests.get(member.display_avatar.url, stream=True)
        avatar = Image.open(raw_avatar.raw).convert("RGBA")
        canvas = ImageDraw.Draw(template)
        name = member.name
        discriminator = member.discriminator
        
        xp_bar_start = (329, 161)
        max_length = 594
        rank_start = (329, 179)

        # Base XP bar
        canvas.rectangle([(xp_bar_start[0], xp_bar_start[1]), (xp_bar_start[0] + max_length, xp_bar_start[1] + 10)], fill="#1f2124")
        
        if XP_DATA:
            user_level = XP_DATA["Level"]
            user_xp = XP_DATA["XP"]
            user_rank = await self.get_rank(member)
            if user_level != 0:
                difference =  await Levels.get_required_xp(user_level + 1) - await Levels.get_required_xp(user_level)
                percentage = (user_xp - await Levels.get_required_xp(user_level)) / difference
            else:
                percentage = user_xp / 100
            xp_bar = percentage * max_length
            canvas.rectangle([(xp_bar_start[0], xp_bar_start[1]), (xp_bar_start[0] + xp_bar, xp_bar_start[1] + 10)], fill="#dc3545")
        else:
            user_level = "N/A"
            user_xp = "N/A"
            user_rank = "N/A"


        namelength = ImageFont.truetype("./assets/fonts/Bebas.ttf", size=75).getsize("{}#{}".format(name, discriminator))[0]
        scaling = (1 - ((namelength - max_length) / namelength)) if namelength > max_length else 1
        
        # Member name
        y_offset = ImageFont.truetype("./assets/fonts/Bebas.ttf", size=round(75 * scaling)).getsize(str(member.name))[1]
        canvas.text((xp_bar_start[0], xp_bar_start[1] - 14 - y_offset), str(member.name), fill="rgb(255, 255, 255)", font=ImageFont.truetype("./assets/fonts/Bebas.ttf", size=round(75 * scaling)))
        
        # Discriminator 
        x_offset =  ImageFont.truetype("./assets/fonts/Bebas.ttf", size=round(75 * scaling)).getsize(str(member.name))[0]
        y_offset = ImageFont.truetype("./assets/fonts/Bebas.ttf", size=round(75 * scaling)).getsize(str(member.name))[1]
        canvas.text((xp_bar_start[0] + x_offset, xp_bar_start[1] - 14 - y_offset), f"#{member.discriminator}", fill="#dc3545",font=ImageFont.truetype("./assets/fonts/Bebas.ttf", size=round(75 * scaling)))

        # Rank
        canvas.text((xp_bar_start[0], rank_start[1]), f"RANK {user_rank}", fill="#dc3545",font=ImageFont.truetype("./assets/fonts/Bebas.ttf", size=50))

        # Level
        x_offset = ImageFont.truetype("./assets/fonts/Bebas.ttf", size=50).getsize(f"RANK {user_rank}")[0]
        canvas.text((xp_bar_start[0] + x_offset + 10, rank_start[1]), f"LEVEL {user_level}", fill="rgb(80, 80, 80)",font=ImageFont.truetype("./assets/fonts/Bebas.ttf", size=50))
        
        # XP Count
        x_offset = ImageFont.truetype("./assets/fonts/Bebas.ttf", size=50).getsize(f"XP {user_xp}")[0]
        canvas.text(((xp_bar_start[0] + max_length) - x_offset, rank_start[1]), f"XP {user_xp}", fill="rgb(80,80,80)",font=ImageFont.truetype("./assets/fonts/Bebas.ttf", size=50))

        # Avatar 
        avatar_mask = avatar.resize((225, 225), 0)
        template.paste(avatar_mask, (60, 40), mask=avatar_mask)

        tempFile = BytesIO()
        template.save(tempFile, format="PNG", optimize=True)
        tempFile.seek(0)
        return File(tempFile, "rank.png")

    @tasks.loop(seconds=voiceXPInterval)
    async def voice_xp(self):
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                real_members = [member for member in channel.members if not member.bot and not (member.voice.self_mute or member.voice.self_deaf)] 
                print(real_members)
                if len(real_members) >= 2:
                    if len(real_members) > 2:
                        local_multiplier = 0.125 * (len(real_members) - 2)
                    else:
                        local_multiplier = 0
                    xp = round(((local_multiplier + 1) * (self.voice_xp_rate/(60/self.voiceXPInterval)))) * self.global_multiplier
                    for member in real_members:
                        if member.status == Status.online:
                            route = f"/xp/{member.guild.id}/{member.id}"
                            data = await self.get_xp_data(member)
                            print(data)
                            if data is not None:
                                if(datetime.datetime.now() > datetime.datetime.fromtimestamp(data.get("VoiceChannelXPLock", None))):
                                    await self.add_xp(member, xp)
                                    API.post(route, {"VoiceChannelXPLock": (datetime.datetime.now() + datetime.timedelta(seconds=1)).isoformat() })
                            else:
                                await self.add_xp(member, xp)

    # Commands
    @app_commands.command(name="leaderboard", description="Displays the server leaderboard.")
    @app_commands.guilds(DEV_GUILD)
    async def invite(self, interaction: discord.Interaction):
        view=View()
        view.add_item(discord.ui.Button(label="View leaderboard",style=discord.ButtonStyle.link,url=f"https://mocbot.masterofcubesau.com/{interaction.guild.id}/leaderboard"))
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT LEVELS", f"Use the button below to view the server leaderboard.", None), view=view)

    @app_commands.command(name="rank", description="Get your XP.")
    @app_commands.guilds(DEV_GUILD)
    @app_commands.describe(
        member="The member to search for."
    )
    async def rank(self, interaction: discord.Interaction, member: Optional[discord.Member]):
        member = member if member else interaction.user
        await interaction.response.send_message(file=await self.generate_rank_card(member))
        await asyncio.sleep(10)
        await interaction.delete_original_response()

    # XP Commands
    XPGroup = app_commands.Group(name="xp", description="Manages user XP.", guild_ids=[DEV_GUILD.id])
    @XPGroup.command(name="add", description="Adds XP to a user.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        amount="The amount of xp to add.",
        member="The member to add xp to."
    )
    async def add(self, interaction: discord.Interaction, amount: int, member: discord.Member):
        await self.add_xp(member, amount)
        await member.send(embed=self.bot.create_embed("MOCBOT LEVELS", f"**{interaction.user}** has given **{amount} XP** to you in the **{interaction.guild.name}** server.", None))
        await interaction.response.send_message(f"**{amount} XP** has successfully been added to user {member.mention}.", ephemeral=True)
    
    @XPGroup.command(name="remove", description="Removes XP from a user.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        amount="The amount of xp to remove.",
        member="The member to remove xp from."
    )
    async def remove(self, interaction: discord.Interaction, amount: int, member: discord.Member):
        await self.add_xp(member, -amount)
        await member.send(embed=self.bot.create_embed("MOCBOT LEVELS", f"**{interaction.user}** has removed **{amount} XP** from you in the **{interaction.guild.name}** server.", None))
        await interaction.response.send_message(f"**{amount} XP** has successfully been removed from user(s) {member.mention}.", ephemeral=True)
    
    @XPGroup.command(name="set", description="Sets the XP of a user.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        value="The value to set the XP to.",
        member="The member to have their XP set."
    )
    async def set(self, interaction: discord.Interaction, value: int, member: discord.Member):
        await self.set_xp(member, value)
        await member.send(embed=self.bot.create_embed("MOCBOT LEVELS", f"**{interaction.user}** has set your XP in the **{interaction.guild.name}** server to **{value} XP**.", None))
        await interaction.response.send_message(f"The user {member.mention} successfully had their XP set to **{value}**", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Levels(bot))

