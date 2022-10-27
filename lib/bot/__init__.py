from discord.ext import commands
from discord import app_commands
import logging.config
import requests
import logging
import discord
import yaml
import sys
import os




logger = logging.getLogger(__name__)
with open("./config.yml", "r") as f:
    config = yaml.safe_load(f)

DEV_GUILD = discord.Object(id=config["GUILD_IDS"]["DEV"])
MOC_GUILD = discord.Object(id=config["GUILD_IDS"]["MOC"])

from lib.db import MOC_DB
MOC_DB = MOC_DB()

class MOCBOT(commands.Bot):

    def __init__(self, is_dev):
        super().__init__(command_prefix="!", owner_id=169402073404669952, intents=discord.Intents.all(), application_id=(config["APPLICATION_IDS"]["DEVELOPMENT"] if is_dev else config["APPLICATION_IDS"]["PRODUCTION"]))
        self.is_dev = is_dev
        self.mode = "DEVELOPMENT" if is_dev else "PRODUCTION"
        
        
    async def setup_hook(self):
        self.setup_logger()
        self.DB = MOC_DB
        MOC_DB.connect()
        await self.load_cog_manager()
        self.appinfo = await super().application_info()
        self.avatar_url = self.appinfo.icon.url
    
        
    def setup_logger(self):
        logging.config.dictConfig(config["LOGGING"])
        formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d - %H:%M:%S") 
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    # async def load_cogs(self):
    #     for cog in [path.split("\\")[-1][:-3] if os.name == "nt" else path.split("\\")[-1][:-3].split("/")[-1] for path in glob("./lib/cogs/*.py")]:
    #         await self.load_extension(f"lib.cogs.{cog}")

    async def load_cog_manager(self):
        await self.load_extension("lib.cogs.Cogs")

    def run(self):
        super().run(config["TOKENS"][self.mode])


    def create_embed(self, title, description, colour):
        embed = discord.Embed(title=None, description=description, colour=colour if colour else 0xDC3145, timestamp=discord.utils.utcnow())
        embed.set_author(name=title if title else None, icon_url=self.avatar_url)
        return embed

    #  Doesn't work, need to look into
    @staticmethod
    def has_permissions(**perms):
        original = app_commands.checks.has_permissions(**perms)
        async def extended_check(interaction):
            if interaction.guild is None:
                return False
            return interaction.user.id in config["DEVELOPERS"] or (interaction.user.id == 169402073404669952) or await original.predicate(interaction)
        return app_commands.check(extended_check)

    @staticmethod
    def is_developer(interaction: discord.Interaction):
        return interaction.user.id in config["Developers"]

    async def on_ready(self):
        self.appinfo = await super().application_info()
        self.avatar_url = self.appinfo.icon.url
        # os.system("cls" if os.name == "nt" else "clear")
        logger.info(
            f"Connected on {self.user.name} ({self.mode}) | d.py v{str(discord.__version__)}"
        )

    async def on_interaction(self, interaction):
        logger.info(f"[COMMAND] [{interaction.guild} // {interaction.guild.id}] {interaction.user} ({interaction.user.id}) used command {interaction.command.name}")

    async def on_message(self, message):
        await self.wait_until_ready()
        if(isinstance(message.channel, discord.DMChannel) and message.author.id == self.owner_id):
            message_components = message.content.lower().split(" ")
            match message_components[0]:
                case "sync":
                    if len(message_components) == 2:
                        result = await self.tree.sync(guild=discord.Object(id=int(message_components[1])))
                    else:
                        result = await self.tree.sync()
                    await message.channel.send(f"Synced {[command.name for command in result]}")
