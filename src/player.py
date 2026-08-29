import st7789 as ST7789
from mpd import MPDClient
from PIL import Image, ImageDraw

from constants import (
    BACKGROUND_COLOR,
    CONNECTION_PORT,
    DISP_HEIGHT,
    DISP_ROTATION,
    FONT,
    FONT_SIZE,
    FRONT_BG_SLOT,
    TEXT_COLOR,
)


class Player:
    def __init__(self):
        self.client: MPDClient = MPDClient()
        self.client.timeout = 10
        self.client.connect("localhost", CONNECTION_PORT)
        self.client.setvol(10)

        self.album_index = 0
        self.albums = self.get_albums()

        self.artist_index = 0
        self.artists = self.get_artists()

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

    def toggle_play(self):
        status = self.client.status()
        if status.get("state") == "play":
            self.client.pause(1)
        else:
            self.client.play()

    def get_artists(self) -> list[str]:
        artist_json = self.client.list("artist")
        artists = []
        for i in artist_json:
            artists.append(i["artist"])

        return artists

    def get_albums(self) -> list[str]:
        album_dict = self.client.list("album")
        albums = []
        for i in album_dict:
            albums.append(i["album"])

        return albums

    def play_album(self, album: str, artist: str):
        self.client.clear()
        self.client.findadd("album", album, "artist", artist)
        self.client.play()

    def render_albums(self):
        # background
        self._draw.rectangle((0, 0, DISP_HEIGHT, DISP_HEIGHT), BACKGROUND_COLOR)

        for i, album in enumerate(self.albums):
            y_offset = i * FONT_SIZE
            self._draw.text((0, y_offset), album, font=FONT, fill=TEXT_COLOR)

        self._disp.display(self._screen)


if __name__ == "__main__":
    player = Player()
    print(player.get_artists())
    print(player.get_albums())

    player.play_album("In My Mind (Prequel) (Hosted By DJ Drama)", "Pharrell")
    print(player.client.status())

    player.render_albums()
    player.client.close()

    while True:
        player.render_albums()

    player.client.disconnect()
