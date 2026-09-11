import threading
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

# set limits to optimize it for background usage
RESOURCE_LIMITS = [
    "--transfers",
    "1",  # only move 1 file at a time
    "--checkers",
    "2",  # keep CPU usage low during the scanning phase
    "--buffer-size",
    "16M",  # drastically reduce ram usage per transfer
    "--check-first",
    "--bwlimit",
    "2M",
]


class SyncState(str, Enum):
    Sync = "Syncing"
    Download = "Downloading"
    Upload = "Uploading"
    Cancel = "Canceling"


class CloudSync:
    def __init__(self) -> None:
        if not rclone.is_installed():
            print("rclone is not installed")
            raise OSError

        self.sync_process = None

        # Directory information
        self.remote = f"{CLOUD_REMOTE_NAME}:{CLOUD_MUSIC_DIR}"
        self.local = str(MUSIC_DIR)
        self.state = None

        # Progress Bar
        bar_style = Style(color=PROGRESS_BAR_COLOR)
        self.progress_label = TextColumn("")
        self.progress_bar = Progress(
            self.progress_label,
            BarColumn(style=bar_style),
            TransferSpeedColumn(),
        )

        # a mapping of actions and names available to the mp3 player
        self.actions = {
            "Sync Local Data": self._sync,
            "Download Cloud Data": self._download,
            "Upload Local Data": self._upload,
            "Cancel": self._cancel,
        }

    def _update_progress_text(self, desc: str):
        self.progress_label.text_format = desc

    def _sync(self):
        if self.state is not None:
            return
        self._update_progress_text(SyncState.Sync.value)

        args = RESOURCE_LIMITS + [self.local, self.remote]

        self.sync_process = threading.Thread(
            target=rclone.sync,
            args=args,
            kwargs={"pbar": self.progress_bar},
            daemon=True,
        )
        self.sync_process.start()
        self.state = SyncState.Sync

    def _download(self):
        if self.state is not None:
            return
        self._update_progress_text(SyncState.Download.value)

        args = RESOURCE_LIMITS + [self.remote, self.local]

        self.sync_process = threading.Thread(
            target=rclone.copy,
            args=args,
            kwargs={"pbar": self.progress_bar},
            daemon=True,
        )
        self.sync_process.start()
        self.state = SyncState.Download

    def _upload(self):
        if self.state is not None:
            return
        self._update_progress_text(SyncState.Upload.value)

        args = RESOURCE_LIMITS + [self.local, self.remote]

        self.sync_process = threading.Thread(
            target=rclone.copy,
            args=args,
            kwargs={"pbar": self.progress_bar},
            daemon=True,
        )
        self.sync_process.start()
        self.state = SyncState.Upload

    def _cancel(self):
        if self.state is None:
            return
        self.state = SyncState.Cancel
        if self.sync_process is not None and self.sync_process.is_alive():
            self.sync_process.join()
        self.state = None

    def take_action(self, name: str):
        # take an action based on a name that is a key in self.actions
        print(f"Cloud: Running {name}...")
        self.actions[name]()
        print(f"Cloud: finished running {name}.")
