from mpd import MPDClient

from constants import CONNECTION_PORT


class MP3:
    def __init__(self):
        self.client: MPDClient = MPDClient()
        self.client.timeout = 10
        self.client.connect("localhost", CONNECTION_PORT)

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


if __name__ == "__main__":
    mp3 = MP3()
    print(mp3.get_artists())
    print(mp3.get_albums())
