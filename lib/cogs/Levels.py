from discord.ext import commands
from discord.ui import Button, View
from discord import app_commands, File, Object
from lib.bot import config, logger, MOCBOT, DEV_GUILD, MOC_DB
from typing import Literal, Union, Optional
import discord

from PIL import Image, ImageDraw, ImageFont
import requests
import asyncio
from io import BytesIO
import datetime
import math
import json



class Levels(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.global_multiplier = 1
        self.messages_xp = 4

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"[COG] Loaded {self.__class__.__name__}")
        await self.level_integrity()
        await self.update_roles()

    # Helper Functions
    async def get_required_xp(level):
        return (6 * ((level)) ** 2 + 94)
    
    async def calculate_correct_level(self, xp):
        if xp >= 100:
            return int(math.sqrt((xp - 94) / 6))
        else:
            return 0

    async def is_ranked(self, member):
        return bool(MOC_DB.field("SELECT UserID FROM XP WHERE (GuildID = %s AND UserID = %s)", member.guild.id, member.id))
    async def get_xp(self, member):
        return MOC_DB.field("SELECT XP FROM XP WHERE (GuildID = %s AND UserID = %s)", member.guild.id, member.id)
    async def get_level(self, member):
        return MOC_DB.field("SELECT Level FROM XP WHERE (GuildID = %s AND UserID = %s)", member.guild.id, member.id)
    async def get_rank(self, member):
        db_lb = MOC_DB.records("SELECT UserID FROM `XP` WHERE GuildID = %s ORDER BY `XP`.`XP` DESC", member.guild.id)
        if(db_lb):
            member_dict = {}
            counter = 1
            for row in db_lb:
                if row[0] in [x.id for x in member.guild.members]:
                    member_dict[counter] = row[0]
                    counter += 1
            member_dict = {v: k for k, v in member_dict.items()}
            return member_dict[member.id]
        return None

    async def add_xp(self, member, amount: int):
        if await self.is_ranked(member):
            if max(int(await self.get_xp(member) + amount), 0) != 0:
                MOC_DB.execute("UPDATE XP SET XP = %s WHERE UserID = %s AND GuildID = %s", int(await self.get_xp(member) + amount), member.id, member.guild.id)
            else:
                MOC_DB.execute("DELETE FROM XP WHERE GuildID = %s AND UserID = %s", member.guild.id, member.id)
        else:
            if amount > 0:
                MOC_DB.execute("INSERT INTO XP (GuildID, UserID, XP) VALUES (%s, %s, %s)", member.guild.id, member.id, int(amount))

    async def set_xp(self, member, value: int):
        if value > 0:
            current_xp = await self.get_xp(member)
            await self.add_xp(member, value - (current_xp if current_xp is not None else 0))
        else:
            MOC_DB.execute("DELETE FROM XP WHERE GuildID = %s AND UserID = %s", member.guild.id, member.id)

    async def message_xp(self, message):
        xplock = MOC_DB.field(
            "SELECT XPLock FROM XP WHERE UserID = %s AND GuildID = %s",
            message.author.id,
            message.guild.id,
        )
        if xplock:
            if datetime.datetime.utcnow() > datetime.datetime.fromisoformat(str(xplock)):
                await self.add_xp(message.author, self.messages_xp * self.global_multiplier)
                MOC_DB.execute(
                    "UPDATE XP SET XPLock = %s WHERE UserID = %s AND GuildID = %s",
                    (datetime.datetime.utcnow() + datetime.timedelta(seconds=60)).isoformat(),
                    message.author.id,
                    message.guild.id,
                )
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
            await self.level_integrity(message.author)
            await self.update_roles(message.author)

    def keystoint(self, x):
        return {int(k): v for k, v in x.items()}

    async def level_integrity(self, member=None):
        if member and await self.is_ranked(member):
            correct_level = await self.calculate_correct_level(await self.get_xp(member))
            if await self.get_level(member) != correct_level:
                MOC_DB.execute("UPDATE XP SET Level = %s WHERE UserID = %s AND GuildID = %s", correct_level, member.id, member.guild.id)
        else:
            data = MOC_DB.records("SELECT * FROM XP")
            for record in data:
                correct_level = await self.calculate_correct_level(record[2])
                if record[3] != correct_level:
                    MOC_DB.execute("UPDATE XP SET Level = %s WHERE UserID = %s AND GuildID = %s", correct_level, record[1], record[0])

    async def update_roles(self, member=None):
        if member:
            role_map = self.keystoint(json.loads(MOC_DB.field("SELECT LevelRoles FROM Roles WHERE GuildID = %s", member.guild.id)))
            if role_map and await self.is_ranked(member):
                member_level = await self.get_level(member)
                member_roles = member.roles
                low_difference = [
                    role_map[x]
                    for x in role_map
                    if role_map[x] not in [role.id for role in member_roles]
                    and x <= member_level
                ]
                high_difference = [
                    role.id
                    for role in member_roles
                    if role.id in {value: key for key, value in role_map.items()}
                    and {value: key for key, value in role_map.items()}[role.id]
                    > member_level
                ]
                if low_difference:
                    for x in low_difference:
                        await member.add_roles(Object(id=int(x)), reason="Role Adjustment")
                if high_difference:
                    for x in high_difference:
                        await member.remove_roles(Object(id=int(x)), reason="Role Adjustment")
        else:
            data = MOC_DB.records("SELECT * FROM Roles")
            for record in data:
                if (guild := self.bot.get_guild(record[0])) != None:
                    for member in guild.members:
                        await self.update_roles(member)

    async def generate_rank_card(self, member):
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
        
        if await self.is_ranked(member):
            user_level = await self.get_level(member)
            user_xp = await self.get_xp(member)
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

    # Commands
    @app_commands.command(name="leaderboard", description="Displays the server leaderboard.")
  #  @app_commands.guilds(DEV_GUILD)
    async def invite(self, interaction: discord.Interaction):
        view=View()
        view.add_item(discord.ui.Button(label="View leaderboard",style=discord.ButtonStyle.link,url=f"https://mocbot.masterofcubesau.com/{interaction.guild.id}/leaderboard"))
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT LEVELS", f"Use the button below to view the server leaderboard.", None), view=view)

    @app_commands.command(name="rank", description="Get your XP.")
  #  @app_commands.guilds(DEV_GUILD)
    @app_commands.describe(
        member="The member to search for."
    )
    async def rank(self, interaction: discord.Interaction, member: Optional[discord.Member]):
        member = member if member else interaction.user
        await interaction.response.send_message(file=await self.generate_rank_card(member))
        await asyncio.sleep(10)
        await interaction.delete_original_message()


    # XP Commands
    XPGroup = app_commands.Group(name="xp", description="Manages user XP.")

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

