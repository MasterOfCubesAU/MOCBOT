from ast import match_case
from discord.ext import commands
from discord import app_commands
from lib.bot import config, logger, MOCBOT, DEV_GUILD, MOC_DB, MOC_GUILD
from typing import Literal, Union, Optional
import discord

from utils.Lavalink import LavalinkVoiceClient
from utils.MusicFilters import FilterDropdownView, MusicFilters
from utils.MusicQueue import QueueMenu, QueuePagination
import lavalink
import re
import functools
import asyncio
import typing
import datetime
from functools import reduce

class Music(commands.Cog):

    MESSAGE_ALIVE_TIME = 10 #seconds

    def __init__(self, bot):
        self.bot = bot
        self.players = {}

        if not hasattr(bot, 'lavalink'):  # This ensures the client isn't overwritten during cog reloads.
            bot.lavalink = lavalink.Client(bot.user.id)
            bot.lavalink.add_node(config["LAVALINK"]["HOST"], config["LAVALINK"]["PORT"], config["LAVALINK"]["PASS"], 'eu', 'default-node')  # Host, Port, Password, Region, Name
        
        lavalink.add_event_hook(self.track_hook)
        lavalink.add_event_hook(self.next_playing)
        # lavalink.add_event_hook(self.progress_update)

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"[COG] Loaded {self.__class__.__name__}")
        
    async def cog_unload(self):
        """ Cog unload handler. This removes any event hooks that were registered. """
        self.bot.lavalink._event_hooks.clear()
     
    def interaction_ensure_voice(f):
        @functools.wraps(f)
        async def callback(self, interaction: discord.Interaction, *args, **kwargs) -> None:
            await self.ensure_voice(await discord.ext.commands.Context.from_interaction(interaction))
            await f(self, interaction, *args, **kwargs)
        return callback

    async def ensure_voice(self, ctx):
        """ This check ensures that the bot and command author are in the same voice channel. """
        if ctx.guild is None:
            raise commands.CommandInvokeError('This command can only be used inside a Discord server.')
        #  This is essentially the same as `@commands.guild_only()`
        #  except it saves us repeating ourselves (and also a few lines)

        should_connect = ctx.command.name in ('play')

        if not ctx.author.voice or not ctx.author.voice.channel:
            # Our cog_command_error handler catches this and sends it to the voice channel.
            # Exceptions allow us to "short-circuit" command invocation via checks so the
            # execution state of the command goes no further.
            raise commands.CommandInvokeError('Join a voice channel first.')

        v_client = ctx.voice_client
        if not v_client:
            if not should_connect:
                raise commands.CommandInvokeError("MOCBOT isn't connected to a voice channel.")

            permissions = ctx.author.voice.channel.permissions_for(ctx.me)

            if not permissions.connect or not permissions.speak:  # Check user limit too?
                raise commands.CommandInvokeError('I need the `CONNECT` and `SPEAK` permissions.')

            await ctx.author.voice.channel.connect(cls=LavalinkVoiceClient)
        else:
            if v_client.channel.id != ctx.author.voice.channel.id:
                raise commands.CommandInvokeError('You need to be in my voice channel.')
        
        player = self.bot.lavalink.player_manager.create(ctx.guild.id)
        player.store('channel', ctx.channel.id)
        await player.set_volume(10)

    async def track_hook(self, event):
        if isinstance(event, lavalink.events.QueueEndEvent):
            # When this track_hook receives a "QueueEndEvent" from lavalink.py
            # it indicates that there are no tracks left in the player's queue.
            # To save on resources, we can tell the bot to disconnect from the voice channel.
            guild_id = event.player.guild_id
            guild = self.bot.get_guild(guild_id)
            channel = guild.get_channel(self.players[guild_id]["CHANNEL"])
            message = await channel.fetch_message(self.players[guild_id]["MESSAGE_ID"])

            await guild.voice_client.disconnect(force=True)
            await message.delete()
            del self.players[guild_id]
    
    async def next_playing(self, event):
        if isinstance(event, lavalink.events.TrackStartEvent):
            guild_id = event.player.guild_id
            player = event.player
            guild = self.bot.get_guild(guild_id)
            channel = guild.get_channel(self.players[guild_id]["CHANNEL"])
            message = await channel.fetch_message(self.players[guild_id]["MESSAGE_ID"])
            logger.info(f"[MUSIC] [{guild} // {guild_id}] Playing {player.current.title} - {player.current.uri}")
            if guild_id in self.players:
                if player.current.stream:
                    await MusicFilters.clear_all(player)
                embed = self.bot.create_embed("MOCBOT MUSIC", f"> NOW PLAYING: [{player.current.title}]({player.current.uri})", None)
                embed.add_field(name="Duration",value=await self.formatDuration(player.current.duration) if not player.current.stream else "LIVE STREAM",inline=True)
                embed.add_field(name="Uploader", value=player.current.author, inline=True)
                embed.set_image(url=f"https://img.youtube.com/vi/{player.current.identifier}/maxresdefault.jpg")
                embed.add_field(name="\u200b",value="**[LINK TO SOURCE]({})**".format(player.current.uri),inline=False)
                embed.set_footer(text=f"Requested by {guild.get_member(player.current.requester)}")
                await message.edit(embed=embed)
    
    async def progress_update(self, event):
        if isinstance(event, lavalink.events.PlayerUpdateEvent):
            if event.position is not None:
                print(await self.formatDuration(event.position))
    
    async def formatDuration(self, ms):
        return datetime.datetime.utcfromtimestamp(ms / 1000).strftime("%Hh %Mm %Ss")

    async def delay_delete(self, interaction):
        await asyncio.sleep(Music.MESSAGE_ALIVE_TIME)
        await interaction.delete_original_response()
       
    @app_commands.command(name="play", description="Search and play media from YouTube, Spotify, SoundCloud etc.")
    @app_commands.guilds(DEV_GUILD, MOC_GUILD)
    @app_commands.describe(
        query="A search query or URL to the media."
    )
    @interaction_ensure_voice
    async def play(self, interaction: discord.Interaction, query: str):
        """ Searches and plays a song from a given query. """
        await interaction.response.defer(thinking=True)
        # Get the player for this guild from cache.
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        # Remove leading and trailing <>. <> may be used to suppress embedding links in Discord.
        query = query.strip('<>')

        # Check if the user input might be a URL. If it isn't, we can Lavalink do a YouTube search for it instead.
        # SoundCloud searching is possible by prefixing "scsearch:" instead.
        if not re.compile(r'https?://(?:www\.)?.+').match(query):
            query = f'ytsearch:{query}'

        # Get the results for the query from Lavalink.
        results = await player.node.get_tracks(query)

        # Results could be None if Lavalink returns an invalid response (non-JSON/non-200 (OK)).
        # ALternatively, results.tracks could be an empty array if the query yielded no tracks.
        if not results or not results.tracks:
            return await interaction.followup.send('No media matching your search query was found.', ephemeral=True)


        # Valid loadTypes are:
        #   TRACK_LOADED    - single video/direct URL)
        #   PLAYLIST_LOADED - direct URL to playlist)
        #   SEARCH_RESULT   - query prefixed with either ytsearch: or scsearch:.
        #   NO_MATCHES      - query yielded no results
        #   LOAD_FAILED     - most likely, the video encountered an exception during loading.
        if results.load_type == 'PLAYLIST_LOADED':
            tracks = results.tracks
            for track in tracks:
                # Add all of the tracks from the playlist to the queue.
                player.add(requester=interaction.user.id, track=track)
                logger.info(f"[MUSIC] [{interaction.guild} // {interaction.guild.id}] Queued {track.title} - {track.uri}")
        else:
            track = results.tracks[0]
            player.add(requester=interaction.user.id, track=track)
            logger.info(f"[MUSIC] [{interaction.guild} // {interaction.guild.id}] Queued {track.title} - {track.uri}")
        
        if player.current is not None:
            embed = self.bot.create_embed("MOCBOT MUSIC", f"> ADDED TO QUEUE: [{player.queue[-1].title}]({player.queue[-1].uri})", None)
            embed.set_image(url=f"https://img.youtube.com/vi/{player.queue[-1].identifier}/maxresdefault.jpg")
            embed.add_field(name="POSITION",value=len(player.queue),inline=True)
            embed.add_field(name="QUEUE TIME",value=await self.formatDuration(reduce(lambda a, b: a + b, [song.duration if not song.stream else 0 for song in player.queue])),inline=True)
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            await self.delay_delete(interaction)
        else:
            embed = self.bot.create_embed("MOCBOT MUSIC", f"> NOW PLAYING: [{player.queue[0].title}]({player.queue[0].uri})", None)
            embed.add_field(name="Duration",value=await self.formatDuration(player.queue[0].duration) if not player.queue[0].stream else "LIVE STREAM",inline=True)
            embed.add_field(name="Uploader", value=player.queue[0].author, inline=True)
            embed.set_image(url=f"https://img.youtube.com/vi/{player.queue[0].identifier}/maxresdefault.jpg")
            embed.add_field(name="\u200b",value="**[LINK TO SOURCE]({})**".format(player.queue[0].uri),inline=False)
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            message = await interaction.original_response()
            self.players[interaction.guild.id] = {"CHANNEL": interaction.channel.id, "MESSAGE_ID": message.id}
        
        # We don't want to call .play() if the player is playing as that will effectively skip
        # the current track.
        if not player.is_playing:
            await player.play()

    @app_commands.command(name="skip", description="Skips the current media to the next one in queue.")
    @app_commands.guilds(DEV_GUILD, MOC_GUILD)
    @app_commands.describe(
        position="The queue item number to skip to."
    )
    async def skip(self, interaction: discord.Interaction, position: typing.Optional[int] = 1):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"The skip command requires media to be playing first.", None))
            return await self.delay_delete(interaction)
        if position < 1 or position > len(player.queue):
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", "You may only skip to a valid queue item.", None))
            return await self.delay_delete(interaction)
        player.queue = player.queue[position - 1:]
        await player.play()
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"Successfully skipped to track [{player.current.title}]({player.current.uri}).", None))
        await self.delay_delete(interaction)
    
    @app_commands.command(name="queue", description="Retrieve the music queue.")
    @app_commands.guilds(DEV_GUILD, MOC_GUILD)
    async def queue(self, interaction: discord.Interaction):
        pages = QueueMenu(source=QueuePagination(self.bot.lavalink.player_manager.get(interaction.guild.id), interaction=interaction, MusicCls=self), interaction=interaction)
        await pages.start(await discord.ext.commands.Context.from_interaction(interaction))

    @app_commands.command(name="seek", description="Seeks the current song.")
    @app_commands.guilds(DEV_GUILD, MOC_GUILD)
    @app_commands.describe(
        time="The time in seconds to seek to."
    )
    async def seek(self, interaction: discord.Interaction, time: int):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"The seek command requires media to be playing first.", None))
            return await self.delay_delete(interaction)
        if not player.current.is_seekable:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"This media does not support seeking.", None))
            return await self.delay_delete(interaction)
        if time < 0 or time > player.current.duration/1000:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"You may only seek between `0 and {player.current.duration/1000}` seconds.", None))
            return await self.delay_delete(interaction)
        await player.seek(time*1000)
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"Seeked to `{await self.formatDuration(time*1000)}`.", None))
        await self.delay_delete(interaction)
   
    @app_commands.command(name="loop", description="Loop the current media or queue.")
    @app_commands.guilds(DEV_GUILD, MOC_GUILD)
    async def loop(self, interaction: discord.Interaction, type: Literal["Song", "Queue (WIP)"]):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"The loop command requires media to be playing first.", None))
            return await self.delay_delete(interaction)
        match type:
            case "Song":
                player.set_repeat(not player.repeat)
                await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"{type} looping {'enabled' if player.repeat else 'disabled'}.", None))
            case "Queue (WIP)":
                await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"Not implemented yet.", None))
        await self.delay_delete(interaction)


    @app_commands.command(name="disconnect", description="Disconnects the bot from voice.")
    @app_commands.guilds(DEV_GUILD, MOC_GUILD)
    async def disconnect(self, interaction: discord.Interaction):
        """ Disconnects the player from the voice channel and clears its queue. """
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)

        if not interaction.guild.voice_client:
            # We can't disconnect, if we're not connected.
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"MOCBOT isn't connected to a voice channel.", None))
            return await self.delay_delete(interaction)

        if not interaction.user.voice or (player.is_connected and  interaction.user.voice.channel.id != int(player.channel_id)):
            # Abuse prevention. Users not in voice channels, or not in the same voice channel as the bot
            # may not disconnect the bot.
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"You must be in the same channel as MOCBOT to use this command.", None))
            return await self.delay_delete(interaction)

        # Clear the queue to ensure old tracks don't start playing
        # when someone else queues something.
        player.queue.clear()
        # Stop the current track so Lavalink consumes less resources.
        await player.stop()

        if interaction.guild.id in self.players:
            channel = interaction.guild.get_channel(self.players[interaction.guild.id]["CHANNEL"])
            message = await channel.fetch_message(self.players[interaction.guild.id]["MESSAGE_ID"])
            await message.delete()
            del self.players[interaction.guild.id]

        # Disconnect from the voice channel.
        await interaction.guild.voice_client.disconnect(force=True)
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"MOCBOT has been stopped and has disconnected.", None))
        await self.delay_delete(interaction)

    @app_commands.command(name="filters", description="Toggles audio filters")
    @app_commands.guilds(DEV_GUILD, MOC_GUILD)
    async def filters(self,  interaction: discord.Interaction):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"The filters command requires media to be playing first.", None))
            return await self.delay_delete(interaction)
        await interaction.response.send_message(view=FilterDropdownView(player, interaction))

async def setup(bot):
    await bot.add_cog(Music(bot))
