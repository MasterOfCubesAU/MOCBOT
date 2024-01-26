from discord.ext import commands
import logging

import traceback


class ErrorHandler(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.bot.tree.on_error = self.on_app_command_error
        self.logger = logging.getLogger(__name__)
        self.bot.on_error = self.on_error

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")

    async def on_app_command_error(self, interaction, error):
        embed = self.bot.create_embed("MOCBOT ERROR", "An unexpected error has occurred.", 0xFF0000)
        embed.add_field(
            name="ERROR:",
            value="> {}\n\nIf this error is a regular occurrence, please contact the team with `/contact`. This error "
            "has been logged.".format(str(error)),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        self.logger.error(f"[ERROR] Unhandled Error: {error}")
        traceback.print_exc()
        raise error

    async def on_error(self, event, *args, **kwargs):
        self.logger.error(f"[ERROR] Unhandled Error: {event}, {args}, {kwargs}")
        traceback.print_exc()


async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))
