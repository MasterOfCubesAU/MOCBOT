import asyncio
from utils.APIHandler import API
from discord.ext import commands
from utils.ConfigHandler import Config
import logging.config
import logging
import discord
import os

from lib.socket.Socket import Socket

class MOCBOT(commands.Bot):

    def __init__(self, is_dev):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.is_dev = is_dev
        self.mode = "DEVELOPMENT" if is_dev else "PRODUCTION"
        self.developers = API.get("/developers")

    async def setup_hook(self):
        self.setup_logger()
        await self.load_cog_manager()
        self.appinfo = await super().application_info()
        if self.appinfo.icon is not None:
            self.avatar_url = self.appinfo.icon.url
        else:
            self.avatar_url = f"https://cdn.discordapp.com/embed/avatars/{int(self.user.discriminator) % 5}.png"

    def setup_logger(self):
        if not os.path.exists("logs"):
            os.makedirs("logs")
            
        logging.config.dictConfig(Config.fetch()["LOGGING"])
        self.logger = logging.getLogger(__name__)
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler):
                handler.encoding = 'utf-8'
            if handler.name == "file" and os.path.isfile('logs/latest.log'):
                handler.doRollover()
        logging.getLogger('discord').setLevel(logging.DEBUG)

    async def load_cog_manager(self):
        await self.load_extension("lib.cogs.Cogs")

    async def main(self):
        await asyncio.gather(
        super().start(Config.fetch()["TOKENS"][self.mode], reconnect=True),
        Socket.start(self)
    )

    def run(self):
        try:
            asyncio.run(self.main())
        except KeyboardInterrupt:
            self.logger.info(f"MOCBOT is cleaning up processes.")
        finally:
            self.logger.info(f"MOCBOT has been shut down gracefully.")

    def create_embed(self, title, description, colour=None):
        embed = discord.Embed(title=None, description=description,
                              colour=colour if colour else 0xDC3145, timestamp=discord.utils.utcnow())
        embed.set_author(name=title if title else None,
                         icon_url=self.avatar_url)
        return embed
    
    async def is_developer(self, interaction):
        if interaction.user.id not in self.bot.developers:
            await interaction.response.send_message(embed=self.bot.create_embed(
                "MOCBOT SETUP", f"You must be a developer of the bot to be able to access this command.", None), ephemeral=True)
            return False
        return True

    #  Doesn't work, need to look into
    # @staticmethod
    # def has_permissions(**perms):
    #     original = app_commands.checks.has_permissions(**perms)

    #     async def extended_check(interaction):
    #         if interaction.guild is None:
    #             return False
    #         return interaction.user.id in config.fetch()["DEVELOPERS"] or (interaction.user.id == 169402073404669952) or await original.predicate(interaction)
    #     return app_commands.check(extended_check)

    # @staticmethod
    # def is_developer(interaction: discord.Interaction):
    #     return interaction.user.id in config.fetch()["Developers"]

    async def on_ready(self):
        self.appinfo = await super().application_info()
        self.avatar_url = self.appinfo.icon.url
        self.logger.info(
            f"Connected on {self.user.name} ({self.mode}) | d.py v{str(discord.__version__)}"
        )

    async def on_interaction(self, interaction):
        if interaction.type is discord.InteractionType.application_command:
            self.logger.info(
                f"[COMMAND] [{interaction.guild} // {interaction.guild.id}] {interaction.user} ({interaction.user.id}) used command {interaction.command.name}")

    async def on_message(self, message):
        await self.wait_until_ready()
        if (isinstance(message.channel, discord.DMChannel) and message.author.id in self.developers):
            message_components = message.content.lower().split(" ")
            match message_components[0]:
                case "sync":
                    if len(message_components) == 2:
                        result = await self.tree.sync(guild=discord.Object(id=int(message_components[1])))
                    else:
                        result = await self.tree.sync()
                    await message.channel.send(f"Synced {[command.name for command in result]}")
