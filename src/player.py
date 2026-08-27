from mpd import MPDClient

from constants import CONNECTION_PORT


class MP3:
    def __init__(self):
        self.client: MPDClient = MPDClient()
        self.client.timeout = 10
        self.client.connect("localhost", CONNECTION_PORT)
        print(self.get_artists())
        print(self.client.list("album"))

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


if __name__ == "__main__":
    mp3 = MP3()
