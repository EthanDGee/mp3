import time
from collections.abc import Callable
from copy import deepcopy
from enum import Enum
from pathlib import Path

import st7789 as ST7789
from PIL import Image, ImageDraw

from constants import (
    BACKGROUND_COLOR,
    DISP_HEIGHT,
    DISP_ROTATION,
    FRONT_BG_SLOT,
    HEADER_FONT,
    HEADER_SIZE,
    HIGHLIGHT_COLOR,
    TEXT_COLOR,
    TEXT_FONT,
    TEXT_SIZE,
)


# Player state and the associate color
class ScreenState(Enum):
    AlbumSelect = "#F955F9"
    ArtistSelect = "#FF3434"
    DiscographySelect = "#FFCF00"
    SongView = "#000000"
    CloudMenu = "#1E90FF"


class Display:
    def __init__(self) -> None:

        # initialize display
        self._disp = ST7789.ST7789(
            height=DISP_HEIGHT,
            rotation=DISP_ROTATION,
            port=0,
            cs=ST7789.BG_SPI_CS_FRONT,  # BG_SPI_CS_BACK or BG_SPI_CS_FRONT
            dc=9,
            backlight=FRONT_BG_SLOT,
            spi_speed_hz=80 * 1000 * 1000,
            offset_left=0,
            offset_top=0,
        )
        self._screen = Image.new(
            "RGB", (DISP_HEIGHT, DISP_HEIGHT), color=BACKGROUND_COLOR
        )
        self._draw = ImageDraw.Draw(self._screen)
        # previous screen to resurrect screen after timeout
        self._previous_screen = deepcopy(self._screen)
        self._disp.begin()

        self.screen_is_off = False
        self.last_button_press = time.time()

    def reset_screen_timeout(self) -> None:
        self.last_button_press = time.time()

        if self.screen_is_off:
            self.turn_screen_on()

    def turn_screen_on(self) -> None:
        self._previous_screen.paste(self._screen, (0, 0))
        self._disp.display(self._screen)
        self._disp.set_backlight(1)
        self.screen_is_off = False

    def turn_off_screen(self) -> None:
        # Don't do anything if it's already off
        if self.screen_is_off:
            return

        self._disp.set_backlight(0)
        # save the screen to a previous screen back up and draw an all black background to prevent burn in.
        self._previous_screen.paste(self._screen, (0, 0))
        self._draw.rectangle((0, 0, DISP_HEIGHT, DISP_HEIGHT), BACKGROUND_COLOR)
        self._disp.display(self._screen)

        self.screen_is_off = True

    def _render_header(self, header: str, color: str):
        self._draw.rectangle((0, 0, DISP_HEIGHT, HEADER_SIZE), color)
        self._draw.text((0, 0), header, font=HEADER_FONT, fill=BACKGROUND_COLOR)

    def _render_list(
        self,
        items: list[str],
        highlighted_index: int,
        y_offset: int = 0,
        formatter: Callable | None = None,
    ):
        self.screen_is_off = False

        # blot out background
        self._draw.rectangle((0, y_offset, DISP_HEIGHT, DISP_HEIGHT), BACKGROUND_COLOR)

        # set bounds for what albums will be rendered to enable scrolling
        # to make it easy to see if there are albums that are above the current render 2 albums above the current album.

        y_offset = y_offset - TEXT_SIZE

        SELECTION_OFFSET = 1
        RENDERED_COUNT = int(DISP_HEIGHT / TEXT_SIZE) + 1
        first_item = max(highlighted_index - SELECTION_OFFSET, 0)
        last_item = min(highlighted_index + RENDERED_COUNT, len(items))

        for i in range(first_item, last_item):
            item = items[i]
            y_offset += TEXT_SIZE

            if i == highlighted_index:
                self._draw.rectangle(
                    (0, y_offset, DISP_HEIGHT, y_offset + TEXT_SIZE), HIGHLIGHT_COLOR
                )

            text = formatter(item) if formatter is not None else item

            self._draw.text((0, y_offset), text, font=TEXT_FONT, fill=TEXT_COLOR)

        self._disp.display(self._screen)
        self._disp.set_backlight(1)

    def render_song(
        self,
        image_path: Path | None,
        show_song_info: bool = False,
        song_info: dict | None = None,
    ):
        self.screen_is_off = False

        # if possible render image as background
        if image_path is None:
            print("Failed to get album art drawing stale background")
            self._draw.rectangle((0, 0, DISP_HEIGHT, DISP_HEIGHT), BACKGROUND_COLOR)
        else:
            album_art = Image.open(image_path)
            album_art = album_art.resize((DISP_HEIGHT, DISP_HEIGHT))
            self._screen.paste(album_art, (0, 0))

        if show_song_info:
            # display metadata
            song_info = song_info or {}
            title = song_info.get("title", "Unknown Title")
            artist = song_info.get("artist", "Unknown Artist")
            album = song_info.get("album", "Unknown Album")

            center_x = DISP_HEIGHT // 2

            self._draw.text(
                (center_x, int(DISP_HEIGHT * 0.2)),
                title,
                font=TEXT_FONT,
                fill="white",
                stroke_width=2,
                stroke_fill="black",
                anchor="mt",
            )

            self._draw.text(
                (center_x, int(DISP_HEIGHT * 0.4)),
                artist,
                font=TEXT_FONT,
                fill="white",
                stroke_width=2,
                stroke_fill="black",
                anchor="mt",
            )

            self._draw.text(
                (center_x, int(DISP_HEIGHT * 0.6)),
                album,
                font=TEXT_FONT,
                fill="white",
                stroke_width=2,
                stroke_fill="black",
                anchor="mt",
            )

        self._disp.set_backlight(1)
        self._disp.display(self._screen)

    def render_albums(
        self,
        albums: list[str],
        album_index: int,
        current_album: str | None,
        is_playing: bool,
    ):
        self._render_header("Album Select", ScreenState.AlbumSelect.value)

        def format_album_item(album_title) -> str:
            if album_title == current_album:
                selection_indicator = "+ " if is_playing else "- "
                return selection_indicator + album_title
            return album_title

        self._render_list(albums, album_index, HEADER_SIZE, format_album_item)

    def render_artists(self, artists: list[str], artist_index: int):
        self._render_header("Artist Select", ScreenState.ArtistSelect.value)
        self._render_list(artists, artist_index, HEADER_SIZE)

    def render_discography(
        self, current_artist: str, discography: list[str], index: int
    ):
        self._render_header(f"{current_artist}:", ScreenState.DiscographySelect.value)
        self._render_list(discography, index, HEADER_SIZE)

    def render_cloud_menu(self, action_names: list[str], index: int):
        self._render_header("Cloud Settings", ScreenState.CloudMenu.value)
        self._render_list(action_names, index, HEADER_SIZE)
