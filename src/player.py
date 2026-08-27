from mpd import MPDClient

from constants import CONNECTION_PORT


class MP3:
    def __init__(self):
        self.client: MPDClient = MPDClient()
        self.client.timeout = 10
        self.client.connect("localhost", CONNECTION_PORT)
        print(self.client.list("artist"))

    def toggle_play(self):
        status = self.client.status()
        if status.get("state") == "play":
            self.client.pause(1)
        else:
            self.client.play()


if __name__ == "__main__":
    mp3 = MP3()
