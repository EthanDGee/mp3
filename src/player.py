import re
import time
import urllib.parse
from pathlib import Path

from gpiozero import Button
from mpd import ConnectionError as MPDConnectionError
from mpd import MPDClient

from cloud_syncing import CloudSync
from constants import (
    BOUNCE_TIME,
    BUTTONS,
    CONNECTION_PORT,
    CONNECTION_TIMEOUT,
    HELD_BUTTON_DURATION,
    MUSIC_DIR,
    SCREEN_INACTIVITY_THRESHOLD,
    VOLUME_INCREMENT,
)
from display import Display, ScreenState
from utils import (
    decrement_no_wrap,
    decrement_with_wrap,
    increment_no_wrap,
    increment_with_wrap,
)


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

        # initialize display
        self.display = Display()

        # initialize cloud syncing manager
        self.cloud = CloudSync()

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

        self.state = ScreenState.SongView  # assigned temporarily
        self.switch_modes(ScreenState.ArtistSelect)

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
        artist_json = self.client.list("albumartist")
        artists = []
        for i in artist_json:
            artists.append(i["albumartist"])

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

        album_dict = self.client.list("album", "albumartist", artist)

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
            self.client.findadd("album", album, "albumartist", artist)
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

    def _render_albums(self) -> None:
        self.display.render_albums(
            self.albums, self.album_index, self.current_album, self._is_playing_music()
        )

    def _render_artists(self) -> None:
        self.display.render_artists(self.artists, self.artist_index)

    def _render_discography(self) -> None:
        current_artist = self.artists[self.artist_index]
        self.display.render_discography(current_artist, self.discography, self.ui_index)

    def _render_cloud_menu(self) -> None:
        action_names = list(self.cloud.actions.keys())
        self.display.render_cloud_menu(action_names, self.ui_index)

    def _render_song(self, show_song_info: bool = False) -> None:
        image_path = self._get_song_image_path()
        song_info = self.client.currentsong() if show_song_info else None
        self.display.render_song(image_path, show_song_info, song_info)

    def switch_modes(self, new_mode: ScreenState) -> None:
        # don't switch if already in the correct mode

        if new_mode == self.state:
            return

        previous_state = self.state
        self.state = new_mode

        if new_mode == ScreenState.AlbumSelect:
            self._set_album_select_buttons()
            self._render_albums()

        elif new_mode == ScreenState.ArtistSelect:
            self._set_artist_select_buttons()
            self._render_artists()

        elif new_mode == ScreenState.DiscographySelect:
            self._set_discography_select_buttons()
            self._render_discography()

        elif new_mode == ScreenState.SongView:
            self._set_song_view_buttons(previous_state)
            self._render_song()

        elif new_mode == ScreenState.CloudMenu:
            self._set_cloud_menu_buttons()
            self._render_cloud_menu()

    def cycle_modes(self, current_state: ScreenState, forward: bool):
        # go backwards or forwards into the next item in the cycle (with wrapping)
        screen_order = [
            ScreenState.ArtistSelect,
            ScreenState.AlbumSelect,
            ScreenState.CloudMenu,
        ]

        # default to artist select screen if not part of the cycle
        if current_state not in screen_order:
            self.artist_index = 0
            self.switch_modes(ScreenState.ArtistSelect)

        screen_count = len(screen_order)
        current_index = screen_order.index(current_state)

        new_mode = ScreenState.ArtistSelect
        if forward:
            new_mode = screen_order[
                increment_with_wrap(current_index, screen_count - 1)
            ]

        else:
            new_mode = screen_order[
                decrement_with_wrap(current_index, screen_count - 1)
            ]

        # update state info to make sense for the next screen
        if new_mode == ScreenState.ArtistSelect:
            self.artists = self.get_artists()
            self.artist_index = 0
        elif new_mode == ScreenState.AlbumSelect:
            self.albums = self.get_albums()
            self.album_index = 0
        self.switch_modes(new_mode)

    def _unbind_buttons(self) -> None:
        # at base all buttons should simply reset the screen timeout
        def _unbind_button(button: Button) -> None:
            button.when_pressed = self.display.reset_screen_timeout
            button.when_released = None
            button.when_held = self.display.reset_screen_timeout

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
            self.display.reset_screen_timeout()
            self.album_index = increment_no_wrap(self.album_index, len(self.albums) - 1)
            self._render_albums()

        def _move_up():
            self.display.reset_screen_timeout()
            self.album_index = decrement_no_wrap(self.album_index)
            self._render_albums()

        def _play_album():
            self.display.reset_screen_timeout()
            highlighted_album = self.albums[self.album_index]

            if self.current_album != highlighted_album:
                self.current_album = highlighted_album
                self.play_album(highlighted_album)

            self.switch_modes(ScreenState.SongView)

        def _toggle_play():
            self.display.reset_screen_timeout()
            self.toggle_play()
            self._render_albums()

        def _cycle_forward():
            self.display.reset_screen_timeout()
            self.cycle_modes(ScreenState.AlbumSelect, True)

        def _cycle_backward():
            self.display.reset_screen_timeout()
            self.cycle_modes(ScreenState.AlbumSelect, False)

        self._bind_button(self.y_button, _move_up, _cycle_forward)
        self._bind_button(self.x_button, _move_down, _cycle_backward)
        self._bind_button(self.b_button, _play_album, None)
        self._bind_button(self.a_button, _toggle_play, None)

    def _set_artist_select_buttons(self) -> None:
        self._unbind_buttons()

        # Incrementation and decrementing are reversed to account
        # for album ordering on render_albums() going from 0 down
        def _move_down():
            self.display.reset_screen_timeout()
            self.artist_index = increment_no_wrap(
                self.artist_index, len(self.artists) - 1
            )
            self._render_artists()

        def _move_up():
            self.display.reset_screen_timeout()
            self.artist_index = decrement_no_wrap(self.artist_index)
            self._render_artists()

        def _go_to_discography():
            self.display.reset_screen_timeout()
            highlighted_artist = self.artists[self.artist_index]
            self.discography = self.get_discography(highlighted_artist)

            self.switch_modes(ScreenState.DiscographySelect)

        def _toggle_play():
            self.display.reset_screen_timeout()
            self.toggle_play()
            self._render_artists()

        def _cycle_forward():
            self.display.reset_screen_timeout()
            self.cycle_modes(ScreenState.ArtistSelect, True)

        def _cycle_backward():
            self.display.reset_screen_timeout()
            self.cycle_modes(ScreenState.ArtistSelect, False)

        self._bind_button(self.y_button, _move_up, _cycle_forward)
        self._bind_button(self.x_button, _move_down, _cycle_backward)
        self._bind_button(self.b_button, _go_to_discography, None)
        self._bind_button(self.a_button, _toggle_play, None)

    def _set_discography_select_buttons(self) -> None:
        self._unbind_buttons()

        # Incrementation and decrementing are reversed to account
        # for album ordering on render_albums() going from 0 down
        def _move_down():
            self.display.reset_screen_timeout()
            self.ui_index = increment_no_wrap(self.ui_index, len(self.discography) - 1)
            self._render_discography()

        def _move_up():
            self.display.reset_screen_timeout()
            self.ui_index = decrement_no_wrap(self.ui_index)
            self._render_discography()

        def _return_to_artist_select():
            self.display.reset_screen_timeout()
            self.switch_modes(ScreenState.ArtistSelect)

        def _play_album():
            self.display.reset_screen_timeout()
            artist = self.artists[self.artist_index]
            album = self.discography[self.ui_index]
            self.play_album(album=album, artist=artist)
            self.switch_modes(ScreenState.SongView)

        def _toggle_play():
            self.display.reset_screen_timeout()
            self.toggle_play()
            self._render_discography()

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
            self.display.reset_screen_timeout()
            self.ui_index = increment_no_wrap(self.ui_index, total_options - 1)
            self._render_cloud_menu()

        def _move_up():
            self.display.reset_screen_timeout()
            self.ui_index = decrement_no_wrap(self.ui_index)
            self._render_cloud_menu()

        def _activate_cloud_action():
            self.display.reset_screen_timeout()
            actions = list(self.cloud.actions.keys())
            selected_action = actions[self.ui_index]
            self.cloud.take_action(selected_action)
            self._render_cloud_menu()

        def _cycle_forward():
            self.display.reset_screen_timeout()
            self.cycle_modes(ScreenState.CloudMenu, True)

        def _cycle_backward():
            self.display.reset_screen_timeout()
            self.cycle_modes(ScreenState.CloudMenu, False)

        self._bind_button(self.y_button, _move_up, _cycle_forward)
        self._bind_button(self.x_button, _move_down, _cycle_backward)
        self._bind_button(self.b_button, _activate_cloud_action, None)

    def _set_song_view_buttons(self, previous_screen: ScreenState) -> None:
        # previous_screen makes it possible to back track to the menu that song view was entered from.
        self._unbind_buttons()

        def _back_to_previous_screen():
            self.display.reset_screen_timeout()
            print(f"moving to {previous_screen}")
            self.switch_modes(previous_screen)

        def _volume_up():
            self.display.reset_screen_timeout()
            self.client.volume(VOLUME_INCREMENT)

        def _next_song():
            self.display.reset_screen_timeout()
            self.client.next()
            self._render_song()

        def _volume_down():
            self.display.reset_screen_timeout()
            self.client.volume(-VOLUME_INCREMENT)

        def _prev_song():
            self.display.reset_screen_timeout()
            self.client.prev()
            self._render_song()

        def _toggle_play():
            self.display.reset_screen_timeout()
            self.toggle_play()
            show_text = not self._is_playing_music()

            self._render_song(show_text)

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
            if (
                time.time() - player.display.last_button_press
                > SCREEN_INACTIVITY_THRESHOLD
            ):
                player.display.turn_off_screen()

    except KeyboardInterrupt:
        pass
    finally:
        player.client.close()
        player.client.disconnect()
