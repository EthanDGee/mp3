import re
import time
import urllib.parse
from collections.abc import Callable
from copy import deepcopy
from enum import Enum
from pathlib import Path

import st7789 as ST7789
from gpiozero import Button
from mpd import ConnectionError as MPDConnectionError
from mpd import MPDClient
from PIL import Image, ImageDraw

from cloud_syncing import CloudSync
from constants import (
    BACKGROUND_COLOR,
    BOUNCE_TIME,
    BUTTONS,
    CONNECTION_PORT,
    CONNECTION_TIMEOUT,
    DISP_HEIGHT,
    DISP_ROTATION,
    FONT,
    FONT_SIZE,
    FRONT_BG_SLOT,
    HELD_BUTTON_DURATION,
    HIGHLIGHT_COLOR,
    MUSIC_DIR,
    SCREEN_INACTIVITY_THRESHOLD,
    TEXT_COLOR,
    VOLUME_INCREMENT,
)
from utils import (
    decrement_no_wrap,
    decrement_with_wrap,
    increment_no_wrap,
    increment_with_wrap,
)


class PlayerState(Enum):
    AlbumSelect = 0
    ArtistSelect = 1
    DiscographySelect = 2
    SongView = 3
    CloudMenu = 4


class Player:
    def __init__(self) -> None:
        self.client = MPDClient()
        self.client.timeout = CONNECTION_TIMEOUT
        self.client.connect("localhost", CONNECTION_PORT)

        # set sensible defaults for album play
        self.client.setvol(1)
        self.client.repeat(1)
        self.client.random(0)
        self.client.consume(0)
        self.client.single(0)

        # initialize cloud syncing manager
        self.cloud = CloudSync()

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

        # initialize buttons
        self.a_button = Button(
            BUTTONS.A.value,
            pull_up=True,
            bounce_time=BOUNCE_TIME,
            hold_time=HELD_BUTTON_DURATION,
        )
        self.b_button = Button(
            BUTTONS.B.value,
            pull_up=True,
            bounce_time=BOUNCE_TIME,
            hold_time=HELD_BUTTON_DURATION,
        )
        self.x_button = Button(
            BUTTONS.X.value,
            pull_up=True,
            bounce_time=BOUNCE_TIME,
            hold_time=HELD_BUTTON_DURATION,
        )
        self.y_button = Button(
            BUTTONS.Y.value,
            pull_up=True,
            bounce_time=BOUNCE_TIME,
            hold_time=HELD_BUTTON_DURATION,
        )

        # Used to trigger screen turn off after inactivity
        self.last_button_press = time.time()
        self.screen_is_off = False

        # Library Info
        self.albums = self.get_albums()
        self.artists = self.get_artists()
        self.discography: list[str] = []

        # Application State
        self.album_index = 0
        self.artist_index = 0
        self.song_index = 0

        # a general UI index
        self.ui_index = 0

        self.current_album = None

        self.playing: bool = False

        self.state = PlayerState.SongView  # assigned temporarily
        self.switch_modes(PlayerState.CloudMenu)

    def _reset_screen_timeout(self) -> None:
        self.last_button_press = time.time()

        # If the screen was off, wake it up by re-rendering the current state
        if self.screen_is_off:
            if self.state == PlayerState.AlbumSelect:
                self.render_albums()
            elif self.state == PlayerState.SongView:
                self.render_song()

    def _turn_screen(self) -> None:
        self._previous_screen.paste(self._screen, (0, 0))
        self._disp.display(self._screen)
        self._disp.set_backlight(1)
        self.screen_is_off = False

    def _turn_off_screen(self) -> None:
        # Don't do anything if it's already off
        if self.screen_is_off:
            return

        self._disp.set_backlight(0)
        # save the screen to a previous screen back up and draw an all black background to prevent burn in.
        self._previous_screen.paste(self._screen, (0, 0))
        BLACK = (0, 0, 0)
        self._draw.rectangle((0, 0, DISP_HEIGHT, DISP_HEIGHT), BLACK)
        self._disp.display(self._screen)

        self.screen_is_off = True

    def _ensure_connected(self) -> None:
        # checks if the client is connected, if not reconnect
        try:
            self.client.ping()
        except (OSError, MPDConnectionError):
            print("Client not connected. Reconnecting")

            # Safely clear the stale internal socket state before reconnecting
            try:
                self.client.disconnect()
            except (OSError, MPDConnectionError):
                pass

            self.client.connect("localhost", CONNECTION_PORT)

    def _is_playing_music(self) -> bool:
        self._ensure_connected()
        status = self.client.status()
        return status.get("state") == "play"

    def toggle_play(self) -> None:
        self._ensure_connected()
        if self._is_playing_music():
            self.client.pause()
        else:
            self.client.play()

    def get_artists(self) -> list[str]:
        self._ensure_connected()
        artist_json = self.client.list("artist")
        artists = []
        for i in artist_json:
            artists.append(i["artist"])

        artists.sort()
        return artists

    def get_albums(self) -> list[str]:
        self._ensure_connected()
        album_dict = self.client.list("album")
        albums = []
        for i in album_dict:
            albums.append(i["album"])
        albums.sort()

        return albums

    def get_discography(self, artist: str) -> list[str]:
        self._ensure_connected()

        album_dict = self.client.list("album", "artist", artist)

        releases = []
        for i in album_dict:
            releases.append(i["album"])
        releases.sort()

        return releases

    def play_album(self, album: str, artist: str | None = None):
        self._ensure_connected()
        self.client.clear()

        if artist == None:
            self.client.findadd("album", album)
        else:
            self.client.findadd("album", album, "artist", artist)
        self.client.play()

        # add a slight delay to avoid race conditions
        time.sleep(0.2)

    def _get_song_image_path(self) -> Path | None:
        self._ensure_connected()

        song_info = self.client.currentsong()

        # find album directory using file key first then artist  + album
        # as fall back

        album_directory = None

        if "file" in song_info:
            song_file = song_info["file"]

            # trim decorators
            prefix_len = len("local:track:")
            song_file = song_file[prefix_len:]
            song_file = urllib.parse.unquote(song_file)

            album_directory = MUSIC_DIR / Path(song_file).parent
        elif "artist" in song_info and "album" in song_info:
            album_directory = MUSIC_DIR / song_info["artist"] / song_info["album"]
        else:
            print("Failed to get metadata for song image path")
            return None

        # pattern to match all cover images in a file regardless of
        # file name as long as it is a file type readable by
        # PIL
        cover_pattern = re.compile(
            r".+\.(apng|avif|blp|bmp|dib|bpg|dcx|dds|eps|fit|fits|flc|fli|gif|grib|icns|ico|cur|im|jpe|jpeg|jpg|j2c|j2k|jpf|jp2|jpx|jxl|mda|mpo|msp|pcx|pdf|pam|pbm|pgm|pfm|png|ppm|psd|qoi|ras|rgb|rgba|sgi|tga|tpic|tif|tiff|webp|wmf|emf|xbm|xpm)$",
            re.IGNORECASE,
        )

        # loop through file names and try
        if album_directory.exists() and album_directory.is_dir():
            for file in album_directory.iterdir():
                if file.is_file() and cover_pattern.match(file.name):
                    return file

        return None

    def render_song(self, show_song_info: bool = False):
        self.screen_is_off = False

        # if possible render image as background
        image_path = self._get_song_image_path()

        if image_path is None:
            print("Failed to get album art drawing stale background")
            self._draw.rectangle((0, 0, DISP_HEIGHT, DISP_HEIGHT), BACKGROUND_COLOR)
        else:
            album_art = Image.open(image_path)
            album_art = album_art.resize((DISP_HEIGHT, DISP_HEIGHT))
            self._screen.paste(album_art, (0, 0))

        if show_song_info:
            # display metadata
            self._ensure_connected()
            song_info = self.client.currentsong()
            title = song_info.get("title", "Unknown Title")
            artist = song_info.get("artist", "Unknown Artist")
            album = song_info.get("album", "Unknown Album")

            center_x = DISP_HEIGHT // 2

            self._draw.text(
                (center_x, int(DISP_HEIGHT * 0.2)),
                title,
                font=FONT,
                fill="white",
                stroke_width=2,
                stroke_fill="black",
                anchor="mt",
            )

            self._draw.text(
                (center_x, int(DISP_HEIGHT * 0.4)),
                artist,
                font=FONT,
                fill="white",
                stroke_width=2,
                stroke_fill="black",
                anchor="mt",
            )

            self._draw.text(
                (center_x, int(DISP_HEIGHT * 0.6)),
                album,
                font=FONT,
                fill="white",
                stroke_width=2,
                stroke_fill="black",
                anchor="mt",
            )

        self._disp.set_backlight(1)
        self._disp.display(self._screen)

    def render_list(
        self,
        items: list[str],
        highlighted_index: int,
        formatter: Callable | None = None,
    ):
        self.screen_is_off = False

        # background
        self._draw.rectangle((0, 0, DISP_HEIGHT, DISP_HEIGHT), BACKGROUND_COLOR)

        # set bounds for what albums will be rendered to enable scrolling
        # to make it easy to see if there are albums that are above the current render 2 albums above the current album.

        SELECTION_OFFSET = 2
        RENDERED_COUNT = int(DISP_HEIGHT / FONT_SIZE) + 1
        first_item = max(highlighted_index - SELECTION_OFFSET, 0)
        last_item = min(highlighted_index + RENDERED_COUNT, len(items))

        y_offset = -FONT_SIZE

        for i in range(first_item, last_item):
            item = items[i]
            y_offset += FONT_SIZE

            if i == highlighted_index:
                self._draw.rectangle(
                    (0, y_offset, DISP_HEIGHT, y_offset + FONT_SIZE), HIGHLIGHT_COLOR
                )

            text = formatter(item) if formatter is not None else item

            self._draw.text((0, y_offset), text, font=FONT, fill=TEXT_COLOR)

        self._disp.display(self._screen)
        self._disp.set_backlight(1)

    def render_albums(self):
        def format_album_item(album_title) -> str:
            if album_title == self.current_album:
                selection_indicator = "+ " if self._is_playing_music() else "- "
                return selection_indicator + album_title
            return album_title

        self.render_list(self.albums, self.album_index, format_album_item)

    def render_artists(self):
        self.render_list(self.artists, self.artist_index)

    def render_discography(self):
        self.render_list(self.discography, self.ui_index)

    def render_cloud_menu(self):
        action_names = list(self.cloud.actions.keys())
        self.render_list(action_names, self.ui_index)

    def switch_modes(self, new_mode: PlayerState) -> None:
        # don't switch if already in the correct mode
        if new_mode == self.state:
            return

        if new_mode == PlayerState.AlbumSelect:
            self._set_album_select_buttons()
            self.render_albums()

        elif new_mode == PlayerState.ArtistSelect:
            self._set_artist_select_buttons()
            self.render_artists()

        elif new_mode == PlayerState.DiscographySelect:
            self.render_discography()
            self._set_discography_select_buttons()

        elif new_mode == PlayerState.SongView:
            self._set_song_view_buttons(self.state)
            self.render_song()

        elif new_mode == PlayerState.CloudMenu:
            self._set_cloud_menu_buttons()
            self.render_cloud_menu()

        self.state = new_mode

    def cycle_modes(self, current_state: PlayerState, forward: bool):
        # go backwards or forwards into the next item in the cycle (with wrapping)
        screen_order = [
            PlayerState.ArtistSelect,
            PlayerState.AlbumSelect,
            PlayerState.CloudMenu,
        ]

        # default to artist select screen if not part of the cycle
        if current_state not in screen_order:
            self.artist_index = 0
            self.switch_modes(PlayerState.ArtistSelect)

        screen_count = len(screen_order)
        current_index = screen_order.index(current_state)

        new_mode = PlayerState.ArtistSelect
        if forward:
            new_mode = screen_order[
                increment_with_wrap(current_index, screen_count - 1)
            ]

        else:
            new_mode = screen_order[
                decrement_with_wrap(current_index, screen_count - 1)
            ]

        # update state info to make sense for the next screen
        if new_mode == PlayerState.ArtistSelect:
            self.artist_index = 0
        elif new_mode == PlayerState.AlbumSelect:
            self.album_index = 0
        self.switch_modes(new_mode)

    def _unbind_buttons(self) -> None:
        # at base all buttons should simply reset the screen timeout
        def _unbind_button(button: Button) -> None:
            button.when_pressed = self._reset_screen_timeout
            button.when_released = None
            button.when_held = self._reset_screen_timeout

        _unbind_button(self.a_button)
        _unbind_button(self.b_button)
        _unbind_button(self.x_button)
        _unbind_button(self.y_button)

    # python functions are first class but have no type int typing so this meets the standards

    def _bind_button(self, button, short_press, long_press=None) -> None:
        # to avoid firing the when released action after a button has been held
        # we track a boolean field that is linked to the button and toggled by
        # a when_held trigger. This prevents the short_press from being triggered
        # after the held button is released.

        # (Tracked via a local dictionary to bypass gpiozero's strict attributes)
        state = {"was_held": False}

        def handle_long_press():
            state["was_held"] = True
            if long_press:
                long_press()

        def handle_short_press():
            # toggle was_held after the button was released
            if state["was_held"]:
                state["was_held"] = False
            else:
                # It was a short press.
                if short_press:
                    short_press()

        button.when_held = handle_long_press if long_press else None
        button.when_released = handle_short_press

    def _set_album_select_buttons(self) -> None:
        self._unbind_buttons()

        # Incrementation and decrementing are reversed to account
        # for album ordering on render_albums() going from 0 down
        def _move_down():
            self._reset_screen_timeout()
            self.album_index = increment_no_wrap(self.album_index, len(self.albums) - 1)
            self.render_albums()

        def _move_up():
            self._reset_screen_timeout()
            self.album_index = decrement_no_wrap(self.album_index)
            self.render_albums()

        def _play_album():
            self._reset_screen_timeout()
            highlighted_album = self.albums[self.album_index]

            if self.current_album != highlighted_album:
                self.current_album = highlighted_album
                self.play_album(highlighted_album)

            self.switch_modes(PlayerState.SongView)

        def _toggle_play():
            self._reset_screen_timeout()
            self.toggle_play()
            self.render_albums()

        def _cycle_forward():
            self._reset_screen_timeout()
            self.cycle_modes(PlayerState.AlbumSelect, True)

        def _cycle_backward():
            self._reset_screen_timeout()
            self.cycle_modes(PlayerState.AlbumSelect, False)

        self._bind_button(self.y_button, _move_up, _cycle_forward)
        self._bind_button(self.x_button, _move_down, _cycle_backward)
        self._bind_button(self.b_button, _play_album, None)
        self._bind_button(self.a_button, _toggle_play, None)

    def _set_artist_select_buttons(self) -> None:
        self._unbind_buttons()

        # Incrementation and decrementing are reversed to account
        # for album ordering on render_albums() going from 0 down
        def _move_down():
            self._reset_screen_timeout()
            self.artist_index = increment_no_wrap(
                self.artist_index, len(self.artists) - 1
            )
            self.render_artists()

        def _move_up():
            self._reset_screen_timeout()
            self.artist_index = decrement_no_wrap(self.artist_index)
            self.render_artists()

        def _go_to_discography():
            self._reset_screen_timeout()
            highlighted_artist = self.artists[self.artist_index]
            self.discography = self.get_discography(highlighted_artist)

            self.switch_modes(PlayerState.DiscographySelect)

        def _toggle_play():
            self._reset_screen_timeout()
            self.toggle_play()
            self.render_artists()

        def _cycle_forward():
            self._reset_screen_timeout()
            self.cycle_modes(PlayerState.ArtistSelect, True)

        def _cycle_backward():
            self._reset_screen_timeout()
            self.cycle_modes(PlayerState.ArtistSelect, False)

        self._bind_button(self.y_button, _move_up, _cycle_forward)
        self._bind_button(self.x_button, _move_down, _cycle_backward)
        self._bind_button(self.b_button, _go_to_discography, None)
        self._bind_button(self.a_button, _toggle_play, None)

    def _set_discography_select_buttons(self) -> None:
        self._unbind_buttons()

        # Incrementation and decrementing are reversed to account
        # for album ordering on render_albums() going from 0 down
        def _move_down():
            self._reset_screen_timeout()
            self.ui_index = increment_no_wrap(self.ui_index, len(self.discography) - 1)
            self.render_discography()

        def _move_up():
            self._reset_screen_timeout()
            self.ui_index = decrement_no_wrap(self.ui_index)
            self.render_discography()

        def _return_to_artist_select():
            self._reset_screen_timeout()
            self.switch_modes(PlayerState.ArtistSelect)

        def _play_album():
            self._reset_screen_timeout()
            artist = self.artists[self.artist_index]
            album = self.discography[self.ui_index]
            self.play_album(album=album, artist=artist)
            self.switch_modes(PlayerState.SongView)

        def _toggle_play():
            self._reset_screen_timeout()
            self.toggle_play()
            self.render_discography()

        self._bind_button(self.y_button, _move_up, _return_to_artist_select)
        self._bind_button(self.x_button, _move_down, None)
        self._bind_button(self.b_button, _play_album, None)
        self._bind_button(self.a_button, _toggle_play, None)

    def _set_cloud_menu_buttons(self) -> None:
        self._unbind_buttons()

        # Incrementation and decrementing are reversed to account
        # for album ordering on render_albums() going from 0 down
        total_options = len(self.cloud.actions.keys())

        def _move_down():
            self._reset_screen_timeout()
            self.ui_index = increment_no_wrap(self.ui_index, total_options - 1)
            self.render_cloud_menu()

        def _move_up():
            self._reset_screen_timeout()
            self.ui_index = decrement_no_wrap(self.ui_index)
            self.render_cloud_menu()

        def _activate_cloud_action():
            self._reset_screen_timeout()
            actions = list(self.cloud.actions.keys())
            selected_action = actions[self.ui_index]
            self.cloud.take_action(selected_action)
            self.render_cloud_menu()

        def _cycle_forward():
            self._reset_screen_timeout()
            self.cycle_modes(PlayerState.ArtistSelect, True)

        def _cycle_backward():
            self._reset_screen_timeout()
            self.cycle_modes(PlayerState.ArtistSelect, False)

        self._bind_button(self.y_button, _move_up, _cycle_forward)
        self._bind_button(self.x_button, _move_down, _cycle_backward)
        self._bind_button(self.b_button, _activate_cloud_action, None)

    def _set_song_view_buttons(self, previous_screen: PlayerState) -> None:
        # previous_screen makes it possible to back track to the menu that song view was entered from.
        self._unbind_buttons()

        def _back_to_previous_screen():
            self._reset_screen_timeout()
            print(f"moving to {previous_screen}")
            self.switch_modes(previous_screen)

        def _volume_up():
            self._reset_screen_timeout()
            self.client.volume(VOLUME_INCREMENT)

        def _next_song():
            self._reset_screen_timeout()
            self.client.next()
            self.render_song()

        def _volume_down():
            self._reset_screen_timeout()
            self.client.volume(-VOLUME_INCREMENT)

        def _prev_song():
            self._reset_screen_timeout()
            self.client.prev()
            self.render_song()

        def _toggle_play():
            self._reset_screen_timeout()
            self.toggle_play()
            show_text = not self._is_playing_music()

            self.render_song(show_text)

        self._bind_button(self.y_button, _back_to_previous_screen)
        self._bind_button(self.b_button, _volume_up, _next_song)
        self._bind_button(self.a_button, _volume_down, _prev_song)
        self._bind_button(self.x_button, _toggle_play)


if __name__ == "__main__":
    player = Player()

    try:
        # Check every second if the screen should be turned off due to inactivity
        while True:
            time.sleep(0.10)
            if time.time() - player.last_button_press > SCREEN_INACTIVITY_THRESHOLD:
                player._turn_off_screen()

    except KeyboardInterrupt:
        pass
    finally:
        player.client.close()
        player.client.disconnect()
