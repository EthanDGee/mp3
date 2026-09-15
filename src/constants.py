from enum import IntEnum
from pathlib import Path

from PIL import ImageFont

# Modipy
CONNECTION_PORT: int = 6600
CONNECTION_TIMEOUT: int = 10
VOLUME_INCREMENT = 5

# Music Library Info
MUSIC_DIR = Path.home() / "Music"
CLOUD_REMOTE_NAME = "gdrive"
CLOUD_MUSIC_DIR = "Music/mp3"

# Display
DISP_HEIGHT = 240
DISP_ROTATION = 270
BACK_BG_SLOT = 18
FRONT_BG_SLOT = 13


# GPIO
class BUTTONS(IntEnum):
    A = 5
    B = 6
    X = 16
    Y = 24


BOUNCE_TIME = 0.05
HELD_BUTTON_DURATION = 0.5
SCREEN_INACTIVITY_THRESHOLD = 10


# Theming
TEXT_SIZE = 20
TEXT_COLOR = "#ffffff"
TEXT_FONT = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", TEXT_SIZE
)

HEADER_COLOR = "#ffffff"
HEADER_SIZE = 20
HEADER_FONT = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", HEADER_SIZE
)


BACKGROUND_COLOR = "#000000"
HIGHLIGHT_COLOR = "#37A537"
# Needs to be one of the standard 256 colors
PROGRESS_BAR_COLOR = "dodger_blue1"  # #0087ff
