from functools import partial

from gpiozero import Button

from constants import (
    BOUNCE_TIME,
    BUTTONS,
    HELD_BUTTON_DURATION,
)
from display import ScreenState
from utils import (
    decrement_no_wrap,
    increment_no_wrap,
)


class Input:
    def __init__(self, player) -> None:
        self.player = player

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

    def _increment_artist_index(self) -> None:
        self.player.display.reset_screen_timeout()
        self.player.artist_index = increment_no_wrap(
            self.player.artist_index, len(self.player.artists) - 1
        )
        self.player._render_artists()

    def _decrement_artist_index(self) -> None:
        self.player.display.reset_screen_timeout()
        self.player.artist_index = decrement_no_wrap(self.player.artist_index)
        self.player._render_artists()

    def _increment_album_index(self) -> None:
        self.player.display.reset_screen_timeout()
        self.player.album_index = increment_no_wrap(
            self.player.album_index, len(self.player.albums) - 1
        )
        self.player._render_albums()

    def _decrement_album_index(self) -> None:
        self.player.display.reset_screen_timeout()
        self.player.album_index = decrement_no_wrap(self.player.album_index)
        self.player._render_albums()

    def _increment_ui_index(self, max_index: int, render_func) -> None:
        self.player.display.reset_screen_timeout()
        self.player.ui_index = increment_no_wrap(self.player.ui_index, max_index)
        render_func()

    def _decrement_ui_index(self, render_func) -> None:
        self.player.display.reset_screen_timeout()
        self.player.ui_index = decrement_no_wrap(self.player.ui_index)
        render_func()

    def _raise_volume(self) -> None:
        self.player.display.reset_screen_timeout()
        self.player.raise_volume()

    def _lower_volume(self) -> None:
        self.player.display.reset_screen_timeout()
        self.player.lower_volume()

    def _toggle_play(self, render_func) -> None:
        self.player.display.reset_screen_timeout()
        self.player.toggle_play()
        render_func()

    def _cycle(self, current_state: ScreenState, forward: bool) -> None:
        self.player.display.reset_screen_timeout()
        self.player.cycle_modes(current_state, forward)

    def _unbind_buttons(self) -> None:
        # at base all buttons should simply reset the screen timeout
        def _unbind_button(button: Button) -> None:
            button.when_pressed = self.player.display.reset_screen_timeout
            button.when_released = None
            button.when_held = self.player.display.reset_screen_timeout

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
        def _play_album():
            self.player.display.reset_screen_timeout()
            highlighted_album = self.player.albums[self.player.album_index]

            if self.player.current_album != highlighted_album:
                self.player.current_album = highlighted_album
                self.player.play_album(highlighted_album)

            self.player.switch_modes(ScreenState.SongView)

        self._bind_button(
            self.y_button,
            self._decrement_album_index,
            partial(self._cycle, ScreenState.AlbumSelect, True),
        )
        self._bind_button(
            self.x_button,
            self._increment_album_index,
            partial(self._cycle, ScreenState.AlbumSelect, False),
        )
        self._bind_button(self.b_button, _play_album, None)
        self._bind_button(
            self.a_button, partial(self._toggle_play, self.player._render_albums), None
        )

    def _set_artist_select_buttons(self) -> None:
        self._unbind_buttons()

        # Incrementation and decrementing are reversed to account
        # for album ordering on render_albums() going from 0 down
        def _go_to_discography():
            self.player.display.reset_screen_timeout()
            highlighted_artist = self.player.artists[self.player.artist_index]
            self.player.discography = self.player.get_discography(highlighted_artist)

            self.player.switch_modes(ScreenState.DiscographySelect)

        self._bind_button(
            self.y_button,
            self._decrement_artist_index,
            partial(self._cycle, ScreenState.ArtistSelect, True),
        )
        self._bind_button(
            self.x_button,
            self._increment_artist_index,
            partial(self._cycle, ScreenState.ArtistSelect, False),
        )
        self._bind_button(self.b_button, _go_to_discography, None)
        self._bind_button(
            self.a_button, partial(self._toggle_play, self.player._render_artists), None
        )

    def _set_discography_select_buttons(self) -> None:
        self._unbind_buttons()

        # Incrementation and decrementing are reversed to account
        # for album ordering on render_albums() going from 0 down
        def _return_to_artist_select():
            self.player.display.reset_screen_timeout()
            self.player.switch_modes(ScreenState.ArtistSelect)

        def _play_album():
            self.player.display.reset_screen_timeout()
            artist = self.player.artists[self.player.artist_index]
            album = self.player.discography[self.player.ui_index]
            self.player.play_album(album=album, artist=artist)
            self.player.switch_modes(ScreenState.SongView)

        self._bind_button(
            self.y_button,
            partial(self._decrement_ui_index, self.player._render_discography),
            _return_to_artist_select,
        )
        self._bind_button(
            self.x_button,
            partial(
                self._increment_ui_index,
                len(self.player.discography) - 1,
                self.player._render_discography,
            ),
            None,
        )
        self._bind_button(self.b_button, _play_album, None)
        self._bind_button(
            self.a_button,
            partial(self._toggle_play, self.player._render_discography),
            None,
        )

    def _set_cloud_menu_buttons(self) -> None:
        self._unbind_buttons()

        # Incrementation and decrementing are reversed to account
        # for album ordering on render_albums() going from 0 down
        total_options = len(self.player.cloud.actions.keys())

        def _activate_cloud_action():
            self.player.display.reset_screen_timeout()
            actions = list(self.player.cloud.actions.keys())
            selected_action = actions[self.player.ui_index]
            self.player.cloud.take_action(selected_action)
            self.player._render_cloud_menu()

        self._bind_button(
            self.y_button,
            partial(self._decrement_ui_index, self.player._render_cloud_menu),
            partial(self._cycle, ScreenState.CloudMenu, True),
        )
        self._bind_button(
            self.x_button,
            partial(
                self._increment_ui_index,
                total_options - 1,
                self.player._render_cloud_menu,
            ),
            partial(self._cycle, ScreenState.CloudMenu, False),
        )
        self._bind_button(self.b_button, _activate_cloud_action, None)

    def _set_song_view_buttons(self, previous_screen: ScreenState) -> None:
        # previous_screen makes it possible to back track to the menu that song view was entered from.
        self._unbind_buttons()

        def _back_to_previous_screen():
            self.player.display.reset_screen_timeout()
            print(f"moving to {previous_screen}")
            self.player.switch_modes(previous_screen)

        def _next_song():
            self.player.display.reset_screen_timeout()
            self.player.next_song()
            self.player._render_song()

        def _prev_song():
            self.player.display.reset_screen_timeout()
            self.player.prev_song()
            self.player._render_song()

        def _toggle_play():
            self.player.display.reset_screen_timeout()
            self.player.toggle_play()
            show_text = not self.player._is_playing_music()

            self.player._render_song(show_text)

        self._bind_button(self.y_button, _back_to_previous_screen)
        self._bind_button(self.b_button, self._raise_volume, _next_song)
        self._bind_button(self.a_button, self._lower_volume, _prev_song)
        self._bind_button(self.x_button, _toggle_play)
