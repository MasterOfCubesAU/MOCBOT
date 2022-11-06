from email.policy import default
from discord.ext import commands
from discord import app_commands
from lib.bot import config, MOCBOT, DEV_GUILD, MOC_DB, MOC_GUILD
from typing import Literal, Union, Optional
import discord
import logging

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
import requests

class Music(commands.Cog):

    MESSAGE_ALIVE_TIME = 10 #seconds

    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        self.logger = logging.getLogger(__name__)

        if not hasattr(bot, 'lavalink'):  # This ensures the client isn't overwritten during cog reloads.
            bot.lavalink = lavalink.Client(bot.user.id)
            bot.lavalink.add_node(config["LAVALINK"]["HOST"], config["LAVALINK"]["PORT"], config["LAVALINK"]["PASS"], 'eu', 'default-node')  # Host, Port, Password, Region, Name
        
        lavalink.add_event_hook(self.track_hook)
        lavalink.add_event_hook(self.next_playing)
        # lavalink.add_event_hook(self.progress_update)

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")
        
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
            guild = self.bot.get_guild(guild_id)
            player = event.player
            self.logger.info(f"[MUSIC] [{guild} // {guild_id}] Playing {player.current.title} - {player.current.uri}")
            if guild_id in self.players:
                if player.current.stream:
                    await MusicFilters.clear_all(player)
                await self.updateNowPlaying(guild, player)
    
    # Written by Sam https://github.com/sam1357
    async def generateNowPlayingEmbed(self, guild, player):
        loopStatus = ""
        match player.loop:
            case player.LOOP_SINGLE:
                loopStatus = "Looping Song •"
            case player.LOOP_QUEUE:
                loopStatus = "Looping Queue •"
            
        embed = self.bot.create_embed("MOCBOT MUSIC", f"> {'NOW PLAYING' if not player.paused else 'PAUSED'}: [{player.current.title}]({player.current.uri})", None)
        embed.add_field(name="Duration",value=await self.formatDuration(player.current.duration) if not player.current.stream else "LIVE STREAM",inline=True)
        embed.add_field(name="Uploader", value=player.current.author, inline=True)
        embed.set_image(url=await self.getMediaThumbnail(player.current.source_name, player.current.identifier) if not player.paused else "https://mocbot.masterofcubesau.com/static/media/media_paused.png")
        embed.set_footer(text=f"{loopStatus} Requested by {guild.get_member(player.current.requester)}")
        return embed

    async def updateNowPlaying(self, guild, player):
        channel = guild.get_channel(self.players[guild.id]["CHANNEL"])
        message = await channel.fetch_message(self.players[guild.id]["MESSAGE_ID"])
        await message.edit(embed=await self.generateNowPlayingEmbed(guild, player))

    async def progress_update(self, event):
        if isinstance(event, lavalink.events.PlayerUpdateEvent):
            if event.position is not None:
                print(await self.formatDuration(event.position))
    
    async def formatDuration(self, ms):
        return datetime.datetime.utcfromtimestamp(ms / 1000).strftime("%Hh %Mm %Ss")

    async def delay_delete(self, interaction, time):
        await asyncio.sleep(time)
        await interaction.delete_original_response()

    async def getMediaThumbnail(self, provider, identifier):
        match provider:
            case 'youtube':
                if requests.get(f"https://img.youtube.com/vi/{identifier}/maxresdefault.jpg").status_code == 200:
                    return f"https://img.youtube.com/vi/{identifier}/maxresdefault.jpg"
                return "https://mocbot.masterofcubesau.com/static/media/noThumbnail.png"
            case 'spotify':
                return requests.get(f'https://open.spotify.com/oembed?url=spotify:track:{identifier}').json()["thumbnail_url"]
            case 'soundcloud':
                return "https://mocbot.masterofcubesau.com/static/media/noThumbnail.png"
            case 'applemusic':
                return "https://mocbot.masterofcubesau.com/static/media/noThumbnail.png"
            case _:
                return "https://mocbot.masterofcubesau.com/static/media/noThumbnail.png"
       
    @app_commands.command(name="play", description="Search and play media from YouTube, Spotify, SoundCloud, Apple Music etc.")
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
            await interaction.followup.send(embed=self.bot.create_embed("MOCBOT MUSIC", f'No media matching the search query `{query}` was found.', None))
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)

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
                self.logger.info(f"[MUSIC] [{interaction.guild} // {interaction.guild.id}] Queued {track.title} - {track.uri}")
        else:
            track = results.tracks[0]
            player.add(requester=interaction.user.id, track=track)
            self.logger.info(f"[MUSIC] [{interaction.guild} // {interaction.guild.id}] Queued {track.title} - {track.uri}")
        
        if player.current is not None:
            embed = self.bot.create_embed("MOCBOT MUSIC", f"> ADDED TO QUEUE: [{player.queue[-1].title}]({player.queue[-1].uri})", None)
            embed.set_image(url=await self.getMediaThumbnail(player.queue[-1].source_name, player.queue[-1].identifier))
            embed.add_field(name="POSITION",value=len(player.queue),inline=True)
            embed.add_field(name="QUEUE TIME",value=await self.formatDuration(reduce(lambda a, b: a + b, [song.duration if not song.stream else 0 for song in player.queue])),inline=True)
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)
        else:
            embed = self.bot.create_embed("MOCBOT MUSIC", f"> NOW PLAYING: [{player.queue[0].title}]({player.queue[0].uri})", None)
            embed.add_field(name="Duration",value=await self.formatDuration(player.queue[0].duration) if not player.queue[0].stream else "LIVE STREAM",inline=True)
            embed.add_field(name="Uploader", value=player.queue[0].author, inline=True)
            embed.set_image(url=await self.getMediaThumbnail(player.queue[0].source_name, player.queue[0].identifier))
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            message = await interaction.original_response()
            self.players[interaction.guild.id] = {"CHANNEL": interaction.channel.id, "MESSAGE_ID": message.id}
        
        # We don't want to call .play() if the player is playing as that will effectively skip
        # the current track.
        if not player.is_playing:
            await player.play()

    @play.autocomplete('query')
    async def autocomplete_callback(self, interaction: discord.Interaction, current: str):
        if not re.compile(r'https?://(?:www\.)?.+').match(current):
            search = requests.get(f"http://suggestqueries.google.com/complete/search?client=youtube&ds=yt&client=firefox&q={current.replace(' ', '%20')}")
            return [app_commands.Choice(name=result, value=result) for result in search.json()[1]]

    @app_commands.command(name="skip", description="Skips the current media to the next one in queue.")
    @app_commands.describe(
        position="The queue item number to skip to."
    )
    async def skip(self, interaction: discord.Interaction, position: typing.Optional[int] = 1):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"The skip command requires media to be playing first.", None))
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)
        if position < 1 or position > len(player.queue):
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", "You may only skip to a valid queue item.", None))
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)
        player.queue = player.queue[position - 1:]
        await player.play()
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"Successfully skipped to track [{player.current.title}]({player.current.uri}).", None))
        await self.delay_delete(interaction, 5)
    
    @app_commands.command(name="queue", description="Retrieve the music queue.")
    async def queue(self, interaction: discord.Interaction):
        pages = QueueMenu(source=QueuePagination(self.bot.lavalink.player_manager.get(interaction.guild.id), interaction=interaction, MusicCls=self), interaction=interaction)
        await pages.start(await discord.ext.commands.Context.from_interaction(interaction))

    @app_commands.command(name="seek", description="Seeks the current song.")
    @app_commands.describe(
        time="The time in seconds to seek to."
    )
    async def seek(self, interaction: discord.Interaction, time: int):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"The seek command requires media to be playing first.", None))
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)
        if not player.current.is_seekable:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"This media does not support seeking.", None))
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)
        if time < 0 or time > player.current.duration/1000:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"You may only seek between `0 and {player.current.duration/1000}` seconds.", None))
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)
        await player.seek(time*1000)
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"Seeked to `{await self.formatDuration(time*1000)}`.", None))
        await self.delay_delete(interaction, 5)
   
    @app_commands.command(name="loop", description="Loop the current media or queue.")
    @app_commands.guilds(DEV_GUILD)
    async def loop(self, interaction: discord.Interaction, type: Literal["Off", "Song", "Queue"]):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"The loop command requires media to be playing first.", None))
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)
        match type:
            case "Off":
                player.set_loop(0)
                await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"Looping is disabled for the queue.", None))
            case "Song":
                player.set_loop(1)
                await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"Song looping is enabled.", None))
            case "Queue":
                player.set_loop(2)
                await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"Queue looping is enabled.", None))
        await self.updateNowPlaying(interaction.guild, player)
        await self.delay_delete(interaction, 5)

    @app_commands.command(name="disconnect", description="Disconnects the bot from voice.")
    async def disconnect(self, interaction: discord.Interaction):
        """ Disconnects the player from the voice channel and clears its queue. """
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)

        if not interaction.guild.voice_client:
            # We can't disconnect, if we're not connected.
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"MOCBOT isn't connected to a voice channel.", None))
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)

        if not interaction.user.voice or (player.is_connected and  interaction.user.voice.channel.id != int(player.channel_id)):
            # Abuse prevention. Users not in voice channels, or not in the same voice channel as the bot
            # may not disconnect the bot.
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"You must be in the same channel as MOCBOT to use this command.", None))
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)

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
        await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)

    @app_commands.command(name="filters", description="Toggles audio filters")
    async def filters(self,  interaction: discord.Interaction):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"The filters command requires media to be playing first.", None))
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)
        await interaction.response.send_message(view=FilterDropdownView(player, interaction))

    # Written by Sam https://github.com/sam1357
    @app_commands.command(name="pause", description="Pauses the music")
    async def pause(self, interaction: discord.Interaction):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)

        if player is None:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"The pause command requires media to be playing first.", None))
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)
        if player.paused:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"The music queue is already paused. Use the resume command to resume the music.", None))
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)

        await player.set_pause(True)
        guild_id = interaction.guild_id
        guild = self.bot.get_guild(guild_id)
        self.logger.info(f"[MUSIC] [{guild} // {guild_id}] Paused {player.current.title} - {player.current.uri}")
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", "Media has been paused.", None))
        await self.updateNowPlaying(interaction.guild, player)
        await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)

    # Written by Sam https://github.com/sam1357
    @app_commands.command(name="resume", description="Resumes the music")
    async def resume(self, interaction: discord.Interaction):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)

        if player is None:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"The resume command requires media to be playing first.", None))
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)
        if not player.paused:
            await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", f"Media is already playing.", None))
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)

        await player.set_pause(False)
        guild_id = interaction.guild_id
        guild = self.bot.get_guild(guild_id)
        self.logger.info(f"[MUSIC] [{guild} // {guild_id}] Resumed {player.current.title} - {player.current.uri}")
        await interaction.response.send_message(embed=self.bot.create_embed("MOCBOT MUSIC", "Media has been resumed.", None))
        await self.updateNowPlaying(interaction.guild, player)
        await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)

async def setup(bot):
    await bot.add_cog(Music(bot))