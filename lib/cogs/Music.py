from discord.ext import commands
from discord import app_commands
from typing import Literal

from utils.Lavalink import LavalinkVoiceClient
from utils.MusicFilters import FilterDropdownView, MusicFilters
from utils.MusicQueue import QueueMenu, QueuePagination
from utils.MusicLyrics import (
    get_lyrics,
    lyrics_substring,
    LyricsMenu,
    LyricsPagination,
)
from utils.ConfigHandler import Config
from StringProgressBar import progressBar
from spotifysearch.client import Client as SpotifyClient
from lavalink.events import TrackStartEvent, QueueEndEvent, TrackEndEvent
from functools import reduce

import lavalink
import re
import functools
import asyncio
import typing
import datetime
import random
import requests
import discord
import logging


class Music(commands.Cog):

    MESSAGE_ALIVE_TIME = 10  # seconds
    DEFAULT_SEEK_TIME = 15

    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        self.logger = logging.getLogger(__name__)

        # This ensures the client isn't overwritten during cog reloads.
        if not hasattr(bot, "lavalink"):
            bot.lavalink = lavalink.Client(bot.user.id)
            bot.lavalink.add_node(
                Config.fetch()["LAVALINK"]["HOST"],
                Config.fetch()["LAVALINK"]["PORT"],
                Config.fetch()["LAVALINK"]["PASS"],
                "eu",
                "default-node",
            )  # Host, Port, Password, Region, Name

        bot.lavalink.add_event_hooks(self)

    async def cog_load(self):
        self.logger.info(f"[COG] Loaded {self.__class__.__name__}")

    async def cog_unload(self):
        """Cog unload handler. This removes any event hooks that were registered."""
        self.bot.lavalink._event_hooks.clear()

    async def send_message(self, interaction, msg, ephemeral=False):
        await interaction.response.send_message(
            embed=self.bot.create_embed("MOCBOT MUSIC", msg),
            ephemeral=ephemeral,
        )
        if not ephemeral:
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)

    def queue_length_msg(self, player):
        return (
            f"There {'is' if len(player.queue) == 1 else 'are'} **{len(player.queue)}** "
            f"track{'' if len(player.queue) == 1 else 's'} in the queue."
        )

    def interaction_ensure_voice(f):
        @functools.wraps(f)
        async def callback(self, interaction: discord.Interaction, *args, **kwargs) -> None:
            if await self.ensure_voice(interaction):
                await f(self, interaction, *args, **kwargs)

        return callback

    async def ensure_voice(self, interaction):
        """This check ensures that the bot and command author are in the same voice channel."""
        if interaction.guild is None:
            raise commands.CommandInvokeError("This command can only be used inside a Discord server.")
        #  This is essentially the same as `@commands.guild_only()`
        #  except it saves us repeating ourselves (and also a few lines)

        should_connect = interaction.command.name in ("play")

        if not interaction.user.voice or not interaction.user.voice.channel:
            await self.send_message(interaction, "Join a voice channel first", True)
            return False

        v_client = interaction.guild.voice_client
        if not v_client:
            if not should_connect:
                await self.send_message(
                    interaction,
                    "MOCBOT is not connected to a voice channel.",
                    True,
                )
                return False

            permissions = interaction.user.voice.channel.permissions_for(interaction.guild.me)

            if not permissions.connect or not permissions.speak:  # Check user limit too?
                await self.send_message(
                    interaction,
                    "Please provide MOCBOT with the CONNECT and SPEAK permissions.",
                    True,
                )
                return False
            await interaction.user.voice.channel.connect(cls=LavalinkVoiceClient)
        else:
            if v_client.channel.id != interaction.user.voice.channel.id:
                await self.send_message(
                    interaction,
                    "You need to be in my voice channel to execute that command.",
                    True,
                )
                return False

        player = self.bot.lavalink.player_manager.create(interaction.guild.id)
        player.store("channel", interaction.channel.id)
        await player.set_volume(10)
        return True

    @lavalink.listener(QueueEndEvent)
    async def queue_end_hook(self, event: QueueEndEvent):
        guild_id = event.player.guild_id
        guild = self.bot.get_guild(guild_id)
        player = event.player
        track = player.fetch("last_track")

        if guild_id not in self.players:
            return

        if player.fetch("autoplay"):
            player = event.player
            results = None

            if not Music.is_youtube_url(track.uri):
                youtube_res = await player.node.get_tracks(f"ytsearch:{track.title} {track.author}")
                track = youtube_res.tracks[0]
                results = await player.node.get_tracks(track.uri + f"&list=RD{track.identifier}")
            else:
                results = await player.node.get_tracks(track.uri + f"&list=RD{track.identifier}")
            if not results or not results.tracks:
                await self.disconnect_bot(guild_id)
                raise commands.CommandInvokeError("Auto queueing could not load the next song.")

            track_number = random.randrange(1, len(results.tracks) - 1)
            player.add(requester=None, track=results.tracks[track_number])
            self.logger.info(
                f"[MUSIC] [{guild} // {guild_id}] Auto-queued {results.tracks[track_number].title} - "
                f"{results.tracks[track_number].uri}"
            )
            if not player.is_playing:
                await player.play()
        else:
            # When this track_hook receives a "QueueEndEvent" from lavalink.py
            # it indicates that there are no tracks left in the player's queue.
            # To save on resources, we can tell the bot to disconnect from the voice channel.
            await self.disconnect_bot(guild_id)

    @lavalink.listener(TrackStartEvent)
    async def next_playing_hook(self, event: TrackStartEvent):
        guild_id = event.player.guild_id
        guild = self.bot.get_guild(guild_id)
        player = event.player
        self.logger.info(f"[MUSIC] [{guild} // {guild_id}] Playing {player.current.title} - {player.current.uri}")
        if guild_id in self.players:
            if player.current.stream:
                await MusicFilters.clear_all(player)
            await self.sendNewNowPlaying(guild, player)

    @lavalink.listener(TrackEndEvent)
    async def track_end_hook(self, event: TrackEndEvent):
        event.player.store("last_track", event.track)

    async def disconnect_bot(self, guild_id):
        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(self.players[guild_id]["CHANNEL"])
        message = await self.retrieve_now_playing(channel, guild)
        await guild.voice_client.disconnect(force=True)
        if message is not None:
            await message.delete()
        del self.players[guild_id]

    def convert_to_seconds(time):
        if time is None:
            return -1
        elif re.match(r"^(?:(?:([01]?\d|2[0-3]):)?([0-5]?\d):)?([0-5]?\d)$", time):
            return sum(int(x) * 60**i for i, x in enumerate(reversed(time.split(":"))))
        else:
            return None

    def is_youtube_url(url):
        return re.match(
            r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube(-nocookie)?\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)"
            r"([\w\-]+)(\S+)?$",
            url,
        )

    # Written by Sam https://github.com/sam1357
    async def generateNowPlayingEmbed(self, guild, player, track=None):
        if track is None:
            track = player.current
        modifiers = []
        match player.loop:
            case player.LOOP_SINGLE:
                modifiers.append("• Looping Song")
            case player.LOOP_QUEUE:
                modifiers.append("• Looping Queue")

        if player.fetch("autoplay"):
            modifiers.append("• Auto Playing")

        embed = self.bot.create_embed(
            "MOCBOT MUSIC",
            f"> {'NOW PLAYING' if not player.paused else 'PAUSED'}: [{track.title}]({track.uri})",
            None,
        )
        embed.add_field(
            name="Duration",
            value=(await self.formatDuration(track.duration) if not track.stream else "LIVE STREAM"),
            inline=True,
        )
        embed.add_field(name="Uploader", value=track.author, inline=True)
        embed.add_field(
            name="Modifiers",
            value="{}".format("\n".join(modifiers)),
            inline=False,
        )
        embed.set_image(
            url=(
                await self.getMediaThumbnail(track.source_name, track.identifier)
                if not player.paused
                else "https://mocbot.masterofcubesau.com/static/media/media_paused.png"
            )
        )
        requester = guild.get_member(track.requester)
        embed.set_footer(text=f"Requested by {requester if requester is not None else f'{self.bot.user}'}")
        return embed

    async def updateNowPlaying(self, guild, player):
        channel = guild.get_channel(self.players[guild.id]["CHANNEL"])
        message = await channel.fetch_message(self.players[guild.id]["MESSAGE_ID"])
        await message.edit(embed=await self.generateNowPlayingEmbed(guild, player))

    async def sendNewNowPlaying(self, guild, player):
        channel = guild.get_channel(self.players[guild.id]["CHANNEL"])
        message = await self.retrieve_now_playing(channel, guild)
        if not self.players[guild.id]["FIRST"]:
            if message is not None:
                await message.delete()
            message = await channel.send(embed=await self.generateNowPlayingEmbed(guild, player))
        self.players[guild.id] = {
            "CHANNEL": channel.id,
            "MESSAGE_ID": message.id,
            "FIRST": False,
        }

    async def retrieve_now_playing(self, channel, guild):
        try:
            message = await channel.fetch_message(self.players[guild.id]["MESSAGE_ID"])
        except discord.errors.NotFound:
            return None
        else:
            return message

    async def formatDuration(self, ms):
        return datetime.datetime.utcfromtimestamp(ms / 1000).strftime("%Hh %Mm %Ss")

    async def delay_delete(self, interaction, time):
        await asyncio.sleep(time)
        await interaction.delete_original_response()

    async def getMediaThumbnail(self, provider, identifier):
        match provider:
            case "youtube":
                if requests.get(f"https://img.youtube.com/vi/{identifier}/maxresdefault.jpg").status_code == 200:
                    return f"https://img.youtube.com/vi/{identifier}/maxresdefault.jpg"
                return "https://mocbot.masterofcubesau.com/static/media/noThumbnail.png"
            case "spotify":
                return requests.get(f"https://open.spotify.com/oembed?url=spotify:track:{identifier}").json()[
                    "thumbnail_url"
                ]
            case "soundcloud":
                return "https://mocbot.masterofcubesau.com/static/media/noThumbnail.png"
            case "applemusic":
                return "https://mocbot.masterofcubesau.com/static/media/noThumbnail.png"
            case _:
                return "https://mocbot.masterofcubesau.com/static/media/noThumbnail.png"

    @app_commands.command(
        name="play",
        description="Search and play media from YouTube, Spotify, SoundCloud, Apple Music etc.",
    )
    @app_commands.describe(query="A search query or URL to the media.")
    @interaction_ensure_voice
    async def play(self, interaction: discord.Interaction, query: str):
        """Searches and plays a song from a given query."""
        await interaction.response.defer(thinking=True)
        # Get the player for this guild from cache.
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        # Remove leading and trailing <>. <> may be used to suppress embedding links in Discord.
        query = query.strip("<>")

        # Check if the user input might be a URL. If it isn't, we can Lavalink do a YouTube search for it instead.
        # SoundCloud searching is possible by prefixing "scsearch:" instead.
        if not re.compile(r"https?://(?:www\.)?.+").match(query):
            query = f"ytsearch:{query}"

        # Get the results for the query from Lavalink.
        results = await player.node.get_tracks(query)

        # Results could be None if Lavalink returns an invalid response (non-JSON/non-200 (OK)).
        # ALternatively, results.tracks could be an empty array if the query yielded no tracks.
        if not results or not results.tracks:
            await interaction.followup.send(
                embed=self.bot.create_embed(
                    "MOCBOT MUSIC",
                    f"No media matching the search query `{query}` was found.",
                    None,
                )
            )
            return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)

        # Valid loadTypes are:
        #   TRACK_LOADED    - single video/direct URL)
        #   PLAYLIST_LOADED - direct URL to playlist)
        #   SEARCH_RESULT   - query prefixed with either ytsearch: or scsearch:.
        #   NO_MATCHES      - query yielded no results
        #   LOAD_FAILED     - most likely, the video encountered an exception during loading.
        if results.load_type == lavalink.LoadType.PLAYLIST:
            tracks = results.tracks
            for track in tracks:
                # Add all of the tracks from the playlist to the queue.
                player.add(requester=interaction.user.id, track=track)
                self.logger.info(
                    f"[MUSIC] [{interaction.guild} // {interaction.guild.id}] Queued {track.title} - {track.uri}"
                )
        else:
            track = results.tracks[0]
            player.add(requester=interaction.user.id, track=track)
            self.logger.info(
                f"[MUSIC] [{interaction.guild} // {interaction.guild.id}] Queued {track.title} - {track.uri}"
            )

        if player.current is not None:
            embed = self.bot.create_embed(
                "MOCBOT MUSIC",
                f"> ADDED TO QUEUE: [{player.queue[-1].title}]({player.queue[-1].uri})",
                None,
            )
            embed.set_image(url=await self.getMediaThumbnail(player.queue[-1].source_name, player.queue[-1].identifier))
            embed.add_field(name="POSITION", value=len(player.queue), inline=True)
            duration = reduce(
                lambda a, b: a + b,
                [song.duration if not song.stream else 0 for song in player.queue],
            )
            embed.add_field(
                name="QUEUE TIME",
                value=(await self.formatDuration(duration) if (duration < 86400000) else ">24h"),
                inline=True,
            )
            embed.set_footer(text=f"Requested by {interaction.user}")
            await interaction.followup.send(embed=embed)
            await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME)
        else:
            await interaction.followup.send(
                embed=await self.generateNowPlayingEmbed(interaction.guild, player, player.queue[0])
            )
            message = await interaction.original_response()
            self.players[interaction.guild.id] = {
                "CHANNEL": interaction.channel.id,
                "MESSAGE_ID": message.id,
                "FIRST": True,
            }

        # We don't want to call .play() if the player is playing as that will effectively skip
        # the current track.
        if not player.is_playing:
            await player.play()

    @play.autocomplete("query")
    async def autocomplete_callback(self, interaction: discord.Interaction, current: str):
        if not re.compile(r"https?://(?:www\.)?.+").match(current):
            search = requests.get(
                f"http://suggestqueries.google.com/complete/search?client=youtube&ds=yt&client=firefox&q="
                f"{current.replace(' ', '%20')}"
            )
            return [app_commands.Choice(name=result, value=result) for result in search.json()[1]]

    @app_commands.command(
        name="skip",
        description="Skips the current media to the next one in queue.",
    )
    @app_commands.describe(position="The queue item number to skip to.")
    @interaction_ensure_voice
    async def skip(
        self,
        interaction: discord.Interaction,
        position: typing.Optional[int] = 1,
    ):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None or player.current is None:
            return await self.send_message(
                interaction,
                "The skip command requires media to be playing first.",
                True,
            )
        if position < 1 or (
            position > len(player.queue) and not player.fetch("autoplay") and player.loop == player.LOOP_NONE
        ):
            return await self.send_message(interaction, "You may only skip to a valid queue item.", True)
        player.queue = player.queue[position - 1 :]
        skipped = player.current
        await player.skip()
        await self.send_message(
            interaction,
            f"Successfully skipped the track [{skipped.title}]({skipped.uri}).",
        )

    @app_commands.command(name="queue", description="Retrieve the music queue.")
    async def queue(self, interaction: discord.Interaction):
        pages = QueueMenu(
            source=QueuePagination(
                self.bot.lavalink.player_manager.get(interaction.guild.id),
                interaction=interaction,
                MusicCls=self,
            ),
            interaction=interaction,
        )
        await pages.start(await discord.ext.commands.Context.from_interaction(interaction))

    @app_commands.command(name="seek", description="Seeks the current song.")
    @app_commands.describe(time="The time to seek to. Supported formats: 10 | 1:10 | 1:10:10")
    @interaction_ensure_voice
    async def seek(self, interaction: discord.Interaction, time: str):
        if (time := Music.convert_to_seconds(time)) is None:
            return await self.send_message(
                interaction,
                "Please provide the time to seek in a suitable format.\nExamples: `10 | 1:10 | 1:10:10`",
            )

        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None or player.current is None:
            return await self.send_message(
                interaction,
                "The seek command requires media to be playing first.",
                True,
            )
        if not player.current.is_seekable:
            return await self.send_message(interaction, "This media does not support seeking.", True)
        if time < 0 or time > player.current.duration / 1000:
            return await self.send_message(
                interaction,
                f"You may only seek between `0` and `{player.current.duration/1000}` seconds.",
                True,
            )
        await player.seek(time * 1000)
        await self.send_message(interaction, f"Seeked to `{await self.formatDuration(time*1000)}`.")

    @app_commands.command(name="loop", description="Loop the current media or queue.")
    @interaction_ensure_voice
    async def loop(
        self,
        interaction: discord.Interaction,
        type: Literal["Off", "Song", "Queue"],
    ):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None or player.current is None:
            return await self.send_message(
                interaction,
                "The loop command requires media to be playing first.",
                True,
            )
        match type:
            case "Off":
                player.set_loop(0)
                await self.send_message(interaction, "Looping is disabled for the queue.")
            case "Song":
                player.set_loop(1)
                await self.send_message(interaction, "Song looping has been enabled.")
            case "Queue":
                player.set_loop(2)
                await self.send_message(interaction, "Queue looping has been enabled.")
        await self.updateNowPlaying(interaction.guild, player)

    @app_commands.command(name="disconnect", description="Disconnects the bot from voice.")
    @interaction_ensure_voice
    async def disconnect(self, interaction: discord.Interaction):
        """Disconnects the player from the voice channel and clears its queue."""
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)

        # Clear the queue to ensure old tracks don't start playing
        # when someone else queues something.
        player.queue.clear()
        # Stop the current track so Lavalink consumes less resources.
        await player.stop()

        if interaction.guild.id in self.players:
            channel = interaction.guild.get_channel(self.players[interaction.guild.id]["CHANNEL"])
            message = await self.retrieve_now_playing(channel, interaction.guild)
            if message is not None:
                await message.delete()
            del self.players[interaction.guild.id]

        # Disconnect from the voice channel.
        await interaction.guild.voice_client.disconnect(force=True)
        await self.send_message(interaction, "MOCBOT has been stopped and has disconnected.")

    @app_commands.command(name="stop", description="Stops any media that is playing.")
    @interaction_ensure_voice
    async def stop(self, interaction: discord.Interaction):
        """Stops the player."""
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)

        if not interaction.guild.voice_client:
            # We can't disconnect, if we're not connected.
            await self.send_message(interaction, "MOCBOT isn't connected to a voice channel.", True)

        if not interaction.user.voice or (
            player.is_connected and interaction.user.voice.channel.id != int(player.channel_id)
        ):
            # Abuse prevention. Users not in voice channels, or not in the same voice channel as the bot
            # may not disconnect the bot.
            await self.send_message(
                interaction,
                "You must be in the same channel as MOCBOT to use this command.",
                True,
            )

        player.queue.clear()
        await player.stop()
        # await self.bot.lavalink.player_manager.destroy(interaction.channel.guild.id)

        if interaction.guild.id in self.players:
            channel = interaction.guild.get_channel(self.players[interaction.guild.id]["CHANNEL"])
            message = await self.retrieve_now_playing(channel, interaction.guild)
            if message is not None:
                await message.delete()
            del self.players[interaction.guild.id]

        await self.send_message(interaction, "MOCBOT has been stopped.")

    @app_commands.command(name="filters", description="Toggles audio filters")
    @interaction_ensure_voice
    async def filters(self, interaction: discord.Interaction):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None or player.current is None:
            return await self.send_message(
                interaction,
                "The filters command requires media to be playing first.",
                True,
            )

        await interaction.response.send_message(view=FilterDropdownView(player, interaction))

    # Written by Sam https://github.com/sam1357
    @app_commands.command(name="pause", description="Pauses the music")
    @interaction_ensure_voice
    async def pause(self, interaction: discord.Interaction):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)

        if player is None or player.current is None:
            return await self.send_message(
                interaction,
                "The pause command requires media to be playing first.",
                True,
            )
        if player.paused:
            return await self.send_message(
                interaction,
                "The music queue is already paused. Use the resume command to resume the music.",
                True,
            )

        await player.set_pause(True)
        guild_id = interaction.guild_id
        guild = self.bot.get_guild(guild_id)
        self.logger.info(f"[MUSIC] [{guild} // {guild_id}] Paused {player.current.title} - {player.current.uri}")

        await self.send_message(interaction, "Media has been paused.")
        await self.updateNowPlaying(interaction.guild, player)

    # Written by Sam https://github.com/sam1357
    @app_commands.command(name="resume", description="Resumes the music")
    @interaction_ensure_voice
    async def resume(self, interaction: discord.Interaction):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)

        if player is None or player.current is None:
            return await self.send_message(
                interaction,
                "The resume command requires media to be playing first.",
                True,
            )
        if not player.paused:
            return await self.send_message(interaction, "Media is already playing.", True)

        await player.set_pause(False)
        guild_id = interaction.guild_id
        guild = self.bot.get_guild(guild_id)
        self.logger.info(f"[MUSIC] [{guild} // {guild_id}] Resumed {player.current.title} - {player.current.uri}")

        await self.send_message(interaction, "Media has been resumed.")
        await self.updateNowPlaying(interaction.guild, player)

    @app_commands.command(name="shuffle", description="Shuffles the queue")
    @interaction_ensure_voice
    async def shuffle(self, interaction: discord.Interaction):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)

        if player is None or player.current is None:
            return await self.send_message(
                interaction,
                "The shuffle command requires media to be playing first.",
                True,
            )

        random.shuffle(player.queue)
        await self.send_message(interaction, "Queue has successfully been shuffled.")

    @app_commands.command(
        name="remove",
        description="Removes the given track number(s) from the queue.",
    )
    @app_commands.describe(
        start="The track number to remove from",
        end="The track number to remove to (optional)",
    )
    @interaction_ensure_voice
    async def remove(
        self,
        interaction: discord.Interaction,
        start: int,
        end: typing.Optional[int],
    ):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        removedTrack = None

        if player is None or player.current is None:
            return await self.send_message(
                interaction,
                "The remove command requires media to be playing first.",
                True,
            )
        if start < 1 or start > len(player.queue):
            return await self.send_message(
                interaction,
                f"Please enter a valid track number to remove. {self.queue_length_msg(player)}",
                True,
            )

        if end is None:
            removedTrack = player.queue.pop(start - 1)
            return await self.send_message(
                interaction,
                f"Successfully removed track [{removedTrack.title}]({removedTrack.uri}).",
            )
        else:
            if end < start or end > len(player.queue):
                await self.send_message(
                    interaction,
                    f"Please enter a valid range to remove. {self.queue_length_msg(player)}",
                    True,
                )
            player.queue = player.queue[: start - 1] + player.queue[end:]
            await self.send_message(
                interaction,
                f"Successfully removed **{end - start + 1} track{'' if end - start + 1 == 1 else 's'}** "
                "from the queue.",
            )

    @app_commands.command(
        name="move",
        description="Moves the given track to another position in the queue.",
    )
    @app_commands.describe(
        source="The track number to move",
        destination="The position in the queue to move to",
    )
    @interaction_ensure_voice
    async def move(self, interaction: discord.Interaction, source: int, destination: int):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)

        if player is None or player.current is None:
            return await self.send_message(
                interaction,
                "The move command requires media to be playing first.",
                True,
            )
        if len(player.queue) < 2:
            return await self.send_message(
                interaction,
                "There are less than two songs in the queue, so there are no songs to move.",
                True,
            )
        if source == destination:
            return await self.send_message(
                interaction,
                "You can only move songs to a different position in the queue.",
                True,
            )
        if source < 1 or source > len(player.queue) or destination < 1 or destination > len(player.queue):
            return await self.send_message(
                interaction,
                f"Please enter valid positions in the queue. {self.queue_length_msg()}",
                True,
            )

        player.queue.insert(destination - 1, track := player.queue.pop(source - 1))
        await self.send_message(
            interaction,
            f"Successfully moved track [{track.title}]({track.uri}) to position **{destination}** in the queue.",
        )

    @app_commands.command(
        name="nowplaying",
        description="Sends a message regarding the currently playing song and its progress",
    )
    async def now_playing(self, interaction: discord.Interaction):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)

        if player is None or player.current is None:
            return await self.send_message(
                interaction,
                "The now playing command requires media to be playing first.",
                True,
            )

        progress_bar = progressBar.splitBar(player.current.duration, int(player.position), size=15)
        duration_text = datetime.datetime.utcfromtimestamp(int(player.current.duration) / 1000).strftime("%H:%M:%S")

        embed = self.bot.create_embed(
            "MOCBOT MUSIC",
            f"> NOW PLAYING: [{player.current.title}]({player.current.uri})",
            None,
        )
        embed.add_field(
            name="Requested By",
            value=(f"<@{player.current.requester}>" if player.current.requester is not None else self.bot.user.mention),
            inline=True,
        )
        embed.add_field(name="Uploader", value=player.current.author, inline=True)
        embed.add_field(
            name="Progress",
            value=f'{datetime.datetime.utcfromtimestamp(int(player.position) / 1000).strftime("%H:%M:%S")} '
            f'{progress_bar[0]} {"LIVE STREAM" if player.current.stream else duration_text}',
            inline=False,
        )
        embed.set_thumbnail(url=await self.getMediaThumbnail(player.current.source_name, player.current.identifier))
        await interaction.response.send_message(embed=embed)
        return await self.delay_delete(interaction, Music.MESSAGE_ALIVE_TIME * 2)

    @app_commands.command(
        name="jump",
        description="Jumps to the given track without skipping songs in the queue",
    )
    @app_commands.describe(position="The queue item number to jump to.")
    @interaction_ensure_voice
    async def jump(self, interaction: discord.Interaction, position: int):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None or player.current is None:
            return await self.send_message(
                interaction,
                "The jump command requires media to be playing first.",
                True,
            )
        if position < 1 or position > len(player.queue):
            return await self.send_message(interaction, "You may only jump to a valid queue item.", True)

        player.queue.insert(0, player.queue.pop(position - 1))
        await player.play()
        await self.send_message(
            interaction,
            f"Successfully jumped to track [{player.current.title}]({player.current.uri}).",
        )

    @app_commands.command(name="autoplay", description="Toggles auto playing on or off")
    @interaction_ensure_voice
    async def autoplay(self, interaction: discord.Interaction, type: Literal["Off", "On"]):
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)

        if player is None or player.current is None:
            return await self.send_message(
                interaction,
                "The autoplay command requires media to be playing first.",
                True,
            )
        match type:
            case "Off":
                player.store("autoplay", False)
                await self.send_message(interaction, "Autoplaying has been disabled for the queue.")
            case "On":
                player.store("autoplay", True)
                loop_disabled = False
                if player.loop != player.LOOP_NONE:
                    loop_disabled = True
                    player.set_loop(0)
                await self.send_message(
                    interaction,
                    f"Autoplaying has been enabled{'.' if not loop_disabled else ' and looping has been disabled.'}",
                )
        await self.updateNowPlaying(interaction.guild, player)

    @app_commands.command(name="lyrics", description="Retrieves lyrics for a song")
    @app_commands.describe(
        query="The song to search lyrics for. Leaving this blank will fetch lyrics for the current song."
    )
    async def lyrics(self, interaction: discord.Interaction, query: typing.Optional[str]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        my_client = SpotifyClient(
            Config.fetch()["SPOTIFY"]["CLIENT_ID"],
            Config.fetch()["SPOTIFY"]["CLIENT_SECRET"],
        )

        if (player is None or player.current is None) and query is None:
            return await self.send_message(
                interaction,
                "The lyrics command requires media to be playing first. Alternatively, you can search for lyrics for a "
                "specific song.",
                True,
            )
        search = player.current.title + player.current.author if query is None else query

        tracks = my_client.search(search).get_tracks()
        lyrics = None
        if len(tracks) >= 1:
            lyrics = await get_lyrics(tracks[0].name, tracks[0].artists[0].name)

        if not lyrics and query is None:
            return await self.send_message(
                interaction,
                f"No lyrics were found for **{player.current.title}**",
                True,
            )
        elif not lyrics and query is not None:
            return await self.send_message(
                interaction,
                f"No lyrics were found for **{query}**. Try searching again with the format: `(Song Name) - (Artist)`.",
                True,
            )
        pages = LyricsMenu(
            source=LyricsPagination(
                interaction=interaction,
                lyrics=lyrics_substring(lyrics),
                song=tracks[0].name,
                artist=tracks[0].artists[0].name,
            ),
            interaction=interaction,
        )
        await pages.start(await discord.ext.commands.Context.from_interaction(interaction))

    @app_commands.command(
        name="rewind",
        description="Rewinds the current song. If a time is not provided, this defaults to 15 seconds.",
    )
    @app_commands.describe(time="The amount of time to rewind. Examples: 10 | 1:10 | 1:10:10")
    @interaction_ensure_voice
    async def rewind(self, interaction: discord.Interaction, time: typing.Optional[str]):
        if (converted_time := Music.convert_to_seconds(time)) == -1:
            converted_time = self.DEFAULT_SEEK_TIME
        elif converted_time is None:
            return await self.send_message(
                interaction,
                "Please provide the time to rewind in a suitable format.\nExamples: `10 | 1:10 | 1:10:10`",
                True,
            )

        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None or player.current is None:
            return await self.send_message(
                interaction,
                "The rewind command requires media to be playing first.",
                True,
            )
        if not player.current.is_seekable:
            return await self.send_message(interaction, "The media does not support rewinding.", True)

        new_time = max(0, player.position - converted_time * 1000)
        await player.seek(new_time)
        await self.send_message(
            interaction,
            f"Rewinded `{await self.formatDuration(converted_time * 1000)}` to `{await self.formatDuration(new_time)}`",
        )

    @app_commands.command(
        name="fastforward",
        description="Fast forwards the current song. If a time is not provided, this defaults to 15 seconds.",
    )
    @app_commands.describe(time="The amount of time to fast forward. Examples: 10 | 1:10 | 1:10:10")
    @interaction_ensure_voice
    async def fastforward(self, interaction: discord.Interaction, time: typing.Optional[str]):
        if (converted_time := Music.convert_to_seconds(time)) == -1:
            converted_time = self.DEFAULT_SEEK_TIME
        elif converted_time is None:
            return await self.send_message(
                interaction,
                "Please provide the time to rewind in a suitable format.\nExamples: `10 | 1:10 | 1:10:10`",
                True,
            )

        player = self.bot.lavalink.player_manager.get(interaction.guild.id)
        if player is None or player.current is None:
            return await self.send_message(
                interaction,
                "The fast forward command requires media to be playing first.",
                True,
            )
        if not player.current.is_seekable:
            return await self.send_message(interaction, "The media does not support fast forwarding.", True)

        new_time = player.position + converted_time * 1000
        if new_time > player.current.duration:
            return await self.send_message(
                interaction,
                "The currently playing media only has "
                f"`{await self.formatDuration(player.current.duration - player.position)}` time left.",
                True,
            )

        await player.seek(new_time)
        await self.send_message(
            interaction,
            f"Fast forwarded `{await self.formatDuration(converted_time * 1000)}` to "
            f"`{await self.formatDuration(new_time)}`.",
        )


async def setup(bot):
    await bot.add_cog(Music(bot))
