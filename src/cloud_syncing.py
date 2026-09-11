from enum import Enum

from rclone_python import rclone
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TransferSpeedColumn,
)
from rich.style import Style

from constants import CLOUD_MUSIC_DIR, CLOUD_REMOTE_NAME, MUSIC_DIR, PROGRESS_BAR_COLOR


class SyncState(str, Enum):
    Sync = "Syncing"
    Download = "Downloading"
    Upload = "Uploading"


class CloudSync:
    def __init__(self) -> None:
        if not rclone.is_installed():
            raise OSError
        self.remote = f"{CLOUD_REMOTE_NAME}:{CLOUD_MUSIC_DIR}"
        self.local = str(MUSIC_DIR)
        self.state = None
        bar_style = Style(color=PROGRESS_BAR_COLOR)
        self.progress_label = TextColumn("")
        self.progress_bar = Progress(
            self.progress_label,
            BarColumn(style=bar_style),
            TransferSpeedColumn(),
        )

        # a mapping of actions and names available to the mp3 player
        self.actions = {
            "Sync Local Data": self.sync,
            "Download Cloud Data": self.download,
            "Upload Local Data": self.upload,
        }

    def _update_progress_text(self, desc: str):
        self.progress_label.text_format = desc

    def sync(self):
        if SyncState is None:
            self._update_progress_text(SyncState.Sync.value)
            rclone.sync(self.local, self.remote, pbar=self.progress_bar)
            self.state = SyncState.Sync

    def download(self):
        if SyncState is None:
            self._update_progress_text(SyncState.Download.value)
            rclone.copy(self.remote, self.local, pbar=self.progress_bar)
            self.state = SyncState.Download

    def upload(self):
        if SyncState is None:
            self._update_progress_text(SyncState.Upload.value)
            rclone.copy(self.local, self.remote, pbar=self.progress_bar)
            self.state = SyncState
