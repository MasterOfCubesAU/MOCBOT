from discord.ext import menus
from discord.ui import Button, View
import discord
from functools import reduce
import datetime


class QueueMenu(View, menus.MenuPages):
    def __init__(self, source, interaction, timeout=20):
        super().__init__(timeout=timeout)
        self._source = source
        self.current_page = 0
        self.ctx = None
        self.message = None
        self.interaction = interaction
        self.createButtons()

    async def on_timeout(self) -> None:
        await self.interaction.delete_original_response()

    async def start(self, ctx, *, channel=None, wait=False):
        # We wont be using wait/channel, you can implement them yourself. This is to match the MenuPages signature.
        await self._source._prepare_once()
        self.ctx = ctx
        self.message = await self.send_initial_message(ctx, ctx.channel)

    async def send_initial_message(self, ctx, channel):
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        await self.interaction.response.send_message(**kwargs)
        return await self.interaction.original_response()

    async def show_checked_page(self, page_number, interaction):
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number, interaction)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number, interaction)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def show_page(self, page_number, interaction):
        page = await self._source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        await interaction.response.edit_message(**kwargs)

    async def _get_kwargs_from_page(self, page):
        """This method calls ListPageSource.format_page class"""
        value = await super()._get_kwargs_from_page(page)
        if "view" not in value:
            value.update({"view": self})
        return value

    async def interaction_check(self, interaction):
        """Only allow the author that invoke the command to be able to use the interaction"""
        return interaction.user == self.ctx.author

    def createButtons(self):
        first_button = Button(label="First Page", style=discord.ButtonStyle.gray)
        first_button.callback = self.first_page_callback
        previous_button = Button(label="Previous Page", style=discord.ButtonStyle.gray)
        previous_button.callback = self.previous_page_callback
        next_button = Button(label="Next Page", style=discord.ButtonStyle.gray)
        next_button.callback = self.next_page_callback
        last_button = Button(label="Last Page", style=discord.ButtonStyle.gray)
        last_button.callback = self.last_page_callback
        self.add_item(first_button)
        self.add_item(previous_button)
        self.add_item(next_button)
        self.add_item(last_button)

    async def first_page_callback(self, interaction):
        await self.show_page(0, interaction)

    async def previous_page_callback(self, interaction):
        await self.show_checked_page(self.current_page - 1, interaction)

    async def next_page_callback(self, interaction):
        await self.show_checked_page(self.current_page + 1, interaction)

    async def last_page_callback(self, interaction):
        await self.show_page(self._source.get_max_pages() - 1, interaction)


class QueuePagination(menus.ListPageSource):
    def __init__(self, player, interaction, MusicCls):
        super().__init__(player.queue if player is not None else [], per_page=10)
        self.interaction = interaction
        self.Music = MusicCls
        self.player = player
        self.emptyQueueMsg = "Type `/play [SONG]` to add songs to the queue."

    async def format_duration(self, ms):
        return datetime.datetime.utcfromtimestamp(ms / 1000).strftime("%Hh %Mm %Ss")

    async def format_page(self, menu, entries):
        offset = (menu.current_page * self.per_page) + 1
        now_playing = (
            f"[{self.player.current.title}]({self.player.current.uri})"
            if self.player is not None and self.player.current is not None
            else "N/A"
        )
        queueContent = "{}\n\n**CURRENT QUEUE:**\n{}".format(
            f"> NOW PLAYING: {now_playing}",
            (
                "\n".join(
                    [
                        f"{index}. [{track.title}]({track.uri}) - "
                        f'{await self.Music.format_duration(track.duration) if not track.stream else "LIVE STREAM"}'
                        for index, track in enumerate(entries, start=offset)
                    ]
                )
                if entries
                else self.emptyQueueMsg
            ),
        )
        embed = self.interaction.client.create_embed("MOCBOT MUSIC", queueContent, None)
        if entries:
            duration = reduce(
                lambda a, b: a + b,
                [song.duration if not song.stream else 0 for song in self.player.queue],
            )
            embed.add_field(
                name="**Total Duration**",
                value=(await self.format_duration(duration) if (duration < 86400000) else ">24h"),
                inline=True,
            )
            embed.add_field(
                name="**Total Tracks**",
                value=len(self.player.queue),
                inline=True,
            )
        embed.set_footer(
            text=f"Page {menu.current_page + 1}/{self.get_max_pages() or 1} | Requested by {self.interaction.user}"
        )
        return embed
