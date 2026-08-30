import re
import signal
import time
import urllib.parse
from enum import Enum
from pathlib import Path

import st7789 as ST7789
from mpd import MPDClient
from PIL import Image, ImageDraw
from RPi import GPIO

from constants import (
    BACKGROUND_COLOR,
    BOUNCE_TIME,
    BUTTONS,
    CONNECTION_PORT,
    DISP_HEIGHT,
    DISP_ROTATION,
    FONT,
    FONT_SIZE,
    FRONT_BG_SLOT,
    HIGHLIGHT_COLOR,
    MUSIC_DIR,
    TEXT_COLOR,
)
from utils import decrement_no_wrap, increment_no_wrap


class State(Enum):
    AlbumSelect = 0
    SongView = 1


class Player:
    def __init__(self):
        self.client: MPDClient = MPDClient()
        self.client.timeout = 10
        self.client.connect("localhost", CONNECTION_PORT)
        self.client.setvol(1)

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
        self._disp.begin()

        # initialize gpio
        GPIO.setmode(GPIO.BCM)

        button_indexes = [button.value for button in BUTTONS]
        GPIO.setup(button_indexes, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Library Info
        self.albums: list[str] = self.get_albums()
        self.artists: list[str] = self.get_artists()

        # Application State
        self.album_index = 0
        self.artist_index = 0
        self.song_index = 0

        self.current_album: int | None = None

        self.playing: bool = False

        self.state = State.AlbumSelect  # assigned temporarily
        self.switch_modes(State.SongView)

    def _is_playing_music(self) -> bool:
        status = self.client.status()
        return status.get("state") == "play"

    def toggle_play(self):
        if self._is_playing_music():
            self.client.pause()
        else:
            self.client.play()

    def get_artists(self) -> list[str]:
        artist_json = self.client.list("artist")
        artists = []
        for i in artist_json:
            artists.append(i["artist"])

        artists.sort()
        return artists

    def get_albums(self) -> list[str]:
        album_dict = self.client.list("album")
        albums = []
        for i in album_dict:
            albums.append(i["album"])
        albums.sort()

        return albums

    def play_album(self, album: str, artist: str | None = None):
        self.client.clear()

        if artist == None:
            self.client.findadd("album", album)
            print(f"Started playing {album}")
        else:
            self.client.findadd("album", album, "artist", artist)
            print(f"Started playing {album} by {artist}")
        self.client.play()

    def get_song_image_path(self) -> Path | None:

        print("Getting song image path...")
        song_info = self.client.currentsong()
        print(f"Song Info: {song_info}")

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
            print("Failed to get metadata")
            return None

        print(f"\nAlbum Directory:{album_directory}")
        # pattern to match all cover images in a file regardless of
        # capitialzion pre/postfix as long as it is a file type readable by
        # PIL
        cover_pattern = re.compile(
            r".*cover.*\.(apng|avif|blp|bmp|dib|bpg|dcx|dds|eps|fit|fits|flc|fli|gif|grib|icns|ico|cur|im|jpe|jpeg|jpg|j2c|j2k|jpf|jp2|jpx|jxl|mda|mpo|msp|pcx|pdf|pam|pbm|pgm|pfm|png|ppm|psd|qoi|ras|rgb|rgba|sgi|tga|tpic|tif|tiff|webp|wmf|emf|xbm|xpm)$",
            re.IGNORECASE,
        )

        # loop through file names and try
        if album_directory.exists() and album_directory.is_dir():
            for file in album_directory.iterdir():
                if file.is_file() and cover_pattern.match(file.name):
                    return file

        return None

    def render_song(self):
        # if possible render image as background
        image_path = self.get_song_image_path()

        if image_path is None:
            print("Drawing stale background")
            self._draw.rectangle((0, 0, DISP_HEIGHT, DISP_HEIGHT), BACKGROUND_COLOR)
        else:
            print("Drawing album art")
            album_art = Image.open(image_path)
            album_art = album_art.resize((DISP_HEIGHT, DISP_HEIGHT))
            self._screen.paste(album_art, (0, 0))

        self._disp.display(self._screen)

    def render_albums(self):
        # background
        self._draw.rectangle((0, 0, DISP_HEIGHT, DISP_HEIGHT), BACKGROUND_COLOR)

        for i, album in enumerate(self.albums):
            y_offset = i * FONT_SIZE

            if i == self.album_index:
                self._draw.rectangle(
                    (0, y_offset, DISP_HEIGHT, y_offset + FONT_SIZE), HIGHLIGHT_COLOR
                )

            if i == self.current_album:
                selection_indicator = "- " if self._is_playing_music() else "x "
                self._draw.text(
                    (0, y_offset),
                    selection_indicator + album,
                    font=FONT,
                    fill=TEXT_COLOR,
                )
            else:
                self._draw.text((0, y_offset), album, font=FONT, fill=TEXT_COLOR)

        self._disp.display(self._screen)

    def switch_modes(self, new_mode: State):

        if new_mode == self.state:
            return

        # clear event detects
        for button in BUTTONS:
            GPIO.remove_event_detect(button.value)

        if new_mode == State.AlbumSelect:
            # Incrementation and decrementing are reversed to account
            # for album ordering on render_albums() going from 0 down
            def _move_down(_channel):
                self.album_index = increment_no_wrap(
                    self.album_index, len(self.albums) - 1
                )
                self.render_albums()

            def _move_up(_channel):
                self.album_index = decrement_no_wrap(self.album_index)
                self.render_albums()

            def _play_album(_channel):
                highlighted_album = self.albums[self.album_index]

                if self.current_album == self.album_index:
                    self.toggle_play()
                else:
                    self.current_album = self.album_index
                    self.play_album(highlighted_album)

                self.render_song()

                # add a slight delay to avoid race conditions
                time.sleep(0.1)

            def _toggle_play(_channel):
                self.toggle_play()
                self.render_albums()

            GPIO.add_event_detect(
                BUTTONS.Y.value,
                GPIO.FALLING,
                callback=_move_up,
                bouncetime=BOUNCE_TIME,
            )

            GPIO.add_event_detect(
                BUTTONS.X.value,
                GPIO.FALLING,
                callback=_move_down,
                bouncetime=BOUNCE_TIME,
            )

            GPIO.add_event_detect(
                BUTTONS.B.value,
                GPIO.FALLING,
                callback=_play_album,
                bouncetime=BOUNCE_TIME,
            )

        self.state = new_mode

        # render


if __name__ == "__main__":
    player = Player()

    print(player.client.status())

    song_info = player.client.currentsong()
    # player.play_album("In My Mind (Prequel) (Hosted By DJ Drama)", "Pharrell")
    print(song_info)

    # player.render_albums()
    player.render_song()

    # button callbacks (see switch_modes) run on their own thread and
    # re-render on press; just block the main thread here until killed.
    signal.pause()

    player.client.close()
    player.client.disconnect()
