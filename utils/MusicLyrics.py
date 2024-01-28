from discord.ext import menus
from discord.ui import Button, View
from unidecode import unidecode
from bs4 import BeautifulSoup, UnicodeDammit
from swaglyrics import backend_url

import discord
import re
import aiohttp

brc = re.compile(r'([(\[](feat|ft|From "[^"]*")[^)\]]*[)\]]|- .*)', re.I)
# matches non space or - or alphanumeric characters
aln = re.compile(r"[^ \-a-zA-Z0-9]+")
spc = re.compile(" *- *| +")  # matches one or more spaces
wth = re.compile(r"(?: *\(with )([^)]+)\)")  # capture text after with
# match only latin characters,
nlt = re.compile(r"[^\x00-\x7F\x80-\xFF\u0100-\u017F\u0180-\u024F\u1E00-\u1EFF]")


async def fetch(session, url, **kwargs):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/84.0.4147.89 Safari/537.36"
    }
    async with session.get(url, headers=headers, **kwargs) as resp:
        return await resp.text()


# Generates the URL to search for using the song and artist


def stripper(song, artist) -> str:
    # remove braces and included text with feat and text after '- '
    song = re.sub(brc, "", song).strip()
    ft = wth.search(song)  # find supporting artists if any
    if ft:
        # remove (with supporting artists) from song
        song = song.replace(ft.group(), "")
        ar = ft.group(1)  # the supporting artist(s)
        if "&" in ar:  # check if more than one supporting artist and add them to artist
            artist += f"-{ar}"
        else:
            artist += f"-and-{ar}"
    song_data = artist + "-" + song
    # swap some special characters
    url_data = song_data.replace("&", "and")
    # replace /, !, _ with space to support more songs
    url_data = url_data.replace("/", " ").replace("!", " ").replace("_", " ")
    for ch in ["Ø", "ø"]:
        url_data = url_data.replace(ch, "")
    # remove non-latin characters before unidecode
    url_data = re.sub(nlt, "", url_data)
    url_data = unidecode(url_data)  # convert accents and other diacritics
    # remove punctuation and other characters
    url_data = re.sub(aln, "", url_data)
    # substitute one or more spaces to -
    url_data = re.sub(spc, "-", url_data.strip())
    return url_data


# Gets the actual lyrics and strips all HTML data


async def get_lyrics(song, artist):
    session = aiohttp.ClientSession()
    url_data = stripper(song, artist)  # generate url path using stripper()
    if url_data.startswith("-") or url_data.endswith("-"):
        # url path had either song in non-latin, artist in non-latin, or both
        return None
    # format the url with the url path
    url = f"https://genius.com/{url_data}-lyrics"

    try:
        page = await fetch(session, url, raise_for_status=True)
    except aiohttp.ClientResponseError:
        url_data = await fetch(
            session,
            f"{backend_url}/stripper",
            data={"song": song, "artist": artist},
        )
        if not url_data:
            return None
        url = f"https://genius.com/{url_data}-lyrics"
        page = await fetch(session, url)

    html = BeautifulSoup(page, "html.parser")
    # finding div on Genius containing the lyrics
    lyrics_path = html.find("div", class_="lyrics")
    if lyrics_path:
        lyrics = UnicodeDammit(lyrics_path.get_text().strip()).unicode_markup
    else:
        # hotfix!
        lyrics_path = html.find_all("div", class_=re.compile("^Lyrics__Container"))
        lyrics_data = []
        for x in lyrics_path:
            lyrics_data.append(UnicodeDammit(re.sub("<.*?>", "", str(x).replace("<br/>", "\n"))).unicode_markup)

        lyrics = "\n".join(lyrics_data)
        lyrics = re.sub(r"\[.*\]\n", "", lyrics)
    return lyrics


def lyrics_substring(lyrics):
    start_index = 0
    length = 800
    end_index = 0
    chunks = []
    lyrics += "\n"

    while end_index < len(lyrics):
        end_index = lyrics.rfind("\n", start_index, length + start_index) + 1
        chunks.append(lyrics[start_index:end_index])
        start_index = end_index
    return chunks


class LyricsMenu(View, menus.MenuPages):
    def __init__(self, source, interaction):
        super().__init__()
        self._source = source
        self.current_page = 0
        self.ctx = None
        self.message = None
        self.interaction = interaction
        self.createButtons()

    async def start(self, ctx, *, channel=None, wait=False):
        # We wont be using wait/channel, you can implement them yourself. This is to match the MenuPages signature.
        await self._source._prepare_once()
        self.ctx = ctx
        self.message = await self.send_initial_message()

    async def send_initial_message(self):
        page = await self._source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        await self.interaction.followup.send(**kwargs)
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


class LyricsPagination(menus.ListPageSource):
    def __init__(self, interaction, lyrics, song, artist):
        super().__init__(lyrics, per_page=1)
        self.interaction = interaction
        self.song = song
        self.artist = artist

    async def format_page(self, menu, entries):
        embed = self.interaction.client.create_embed(f"{self.song} by {self.artist} Lyrics", entries, None)
        embed.set_footer(
            text=f"Page {menu.current_page + 1}/{self.get_max_pages() or 1} | Requested by {self.interaction.user}"
        )
        return embed
