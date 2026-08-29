from mpd import MPDClient

from constants import CONNECTION_PORT


class Player:
    def __init__(self):
        self.client: MPDClient = MPDClient()
        self.client.timeout = 10
        self.client.connect("localhost", CONNECTION_PORT)
        self.client.setvol(50)

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


if __name__ == "__main__":
    player = Player()
    print(player.get_artists())
    print(player.get_albums())

    player.play_album("In My Mind (Prequel) (Hosted By DJ Drama)", "Pharrell")
    print(player.client.status())
    player.client.close()
    player.client.disconnect()
