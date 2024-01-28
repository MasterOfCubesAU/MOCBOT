import asyncio
import discord
from lavalink.filters import (
    LowPass,
    Rotation,
    Timescale,
    Vibrato,
    Karaoke,
    Equalizer,
    Tremolo,
)


class FilterDropdown(discord.ui.Select):
    def __init__(self, player, latest_interaction):
        self.player = player
        self.latest_interaction = latest_interaction

        # Set the options that will be presented inside the dropdown
        options = [
            discord.SelectOption(
                label="Nightcore",
                description="Speeds up and raises the pitch of the song.",
                value="nightcore",
            ),
            discord.SelectOption(
                label="Vaporwave",
                description="Time to chill out.",
                value="vapor_wave",
            ),
            discord.SelectOption(
                label="8D Audio",
                description="I'm in your head.",
                value="eight_d",
            ),
            discord.SelectOption(
                label="Vibrato",
                description="Adds a 'wobbly' effect.",
                value="vibrato",
            ),
            discord.SelectOption(
                label="Low Pass",
                description="Club next door too loud?",
                value="low_pass",
            ),
            discord.SelectOption(
                label="Karaoke",
                description="Having a karaoke night?",
                value="karaoke",
            ),
            # discord.SelectOption(label="Ear Rape", description="See title.", value="ear_rape"),
            discord.SelectOption(
                label="Bass Boost",
                description="Bass boosts the song.",
                value="bass_boost",
            ),
        ]

        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the three options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(
            placeholder="Choose some audio filters",
            min_values=0,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values:
            await MusicFilters.clear_all(self.player)
            for filter in self.values:
                await getattr(MusicFilters, filter)(self.player)
        else:
            await MusicFilters.clear_all(self.player)
        await self.latest_interaction.delete_original_response()
        await interaction.response.send_message(
            embed=interaction.client.create_embed(
                "MOCBOT MUSIC",
                (
                    "Applied filters: "
                    f"{', '.join([filter.label for filter in self.options if filter.value in self.values])}"
                    if self.values
                    else "Removed all filters"
                ),
                None,
            )
        )
        await asyncio.sleep(10)
        await interaction.delete_original_response()


class FilterDropdownView(discord.ui.View):
    def __init__(self, player, interaction):
        super().__init__(timeout=60)
        self.player = player
        self.add_item(FilterDropdown(player, interaction))
        self.latest_interaction = interaction

        clear_button = discord.ui.Button(label="Clear Active Filters", style=discord.ButtonStyle.red)
        clear_button.callback = self.clear_button_callback
        self.add_item(clear_button)

    async def clear_button_callback(self, interaction):
        await MusicFilters.clear_all(self.player)
        await self.latest_interaction.delete_original_response()

    async def on_timeout(self):
        await self.latest_interaction.delete_original_response()


class MusicFilters:
    def __init__(self, player) -> None:
        self.player = player
        self.toggled = []

    async def low_pass(player):
        lp_filter = LowPass()
        lp_filter.update(smoothing=50)
        await player.set_filter(lp_filter)

    async def eight_d(player):
        eight_d_filter = Rotation()
        eight_d_filter.update(rotation_hz=0.2)
        await player.set_filter(eight_d_filter)

    async def nightcore(player):
        nightcore_filter = Timescale()
        nightcore_filter.update(speed=1.2, pitch=1.2, rate=1)
        await player.set_filter(nightcore_filter)

    async def vibrato(player):
        vibrato_filter = Vibrato()
        vibrato_filter.update(depth=1, frequency=10)
        await player.set_filter(vibrato_filter)

    async def karaoke(player):
        karaoke_filter = Karaoke()
        karaoke_filter.update(level=0.6, mono_level=0.95)
        await player.set_filter(karaoke_filter)

    async def bass_boost(player):
        bb_filter = Equalizer()
        bb_filter.update(bands=[(0, 0.2), (1, 0.2), (2, 0.2)])
        await player.set_filter(bb_filter)

    async def vapor_wave(player):
        vw_filter = Equalizer()
        vw_filter.update(bands=[(1, 0.3), (0, 0.3)])
        timescale_filter = Timescale()
        timescale_filter.update(pitch=0.7)
        tremolo_filter = Tremolo()
        tremolo_filter.update(depth=0.3, frequency=14)
        await player.set_filter(vw_filter)
        await player.set_filter(timescale_filter)
        await player.set_filter(tremolo_filter)

    async def ear_rape(player):
        # ear_rape_filter = Distortion()
        # ear_rape_filter.update(scale=100)
        # await player.set_filter(ear_rape_filter)
        await player.set_volume(1000)

    async def clear_all(player):
        await player.clear_filters()
        await player.set_volume(10)
