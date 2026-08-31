from enum import IntEnum
from pathlib import Path

from PIL import ImageFont

# Modipy
CONNECTION_PORT: int = 6600
CONNECTION_TIMEOUT: int = 10
VOLUME_INCREMENT = 5

# Music Library Info
MUSIC_DIR = Path.home() / "Music"

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


BOUNCE_TIME = 250
HELD_BUTTON_DURATION = 1000


# Theming
FONT_SIZE = 20
FONT = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", FONT_SIZE
)
BACKGROUND_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 255, 255)
HIGHLIGHT_COLOR = (55, 165, 55)
