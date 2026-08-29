from enum import IntEnum

from PIL import ImageFont

# Modipy
CONNECTION_PORT: int = 6600

# Display
DISP_HEIGHT = 240
DISP_ROTATION = 270
BACK_BG_SLOT = 18
FRONT_BG_SLOT = 19


# Pimoroni
class BUTTONS(IntEnum):
    A = 5
    B = 6
    X = 16
    Y = 24


BOUNCE_TIME = 250

# Theming
FONT_SIZE = 20
FONT = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", FONT_SIZE
)
BACKGROUND_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 255, 255)
HIGHLIGHT_COLOR = (55, 165, 55)
