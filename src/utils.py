import subprocess

from PIL import Image, ImageDraw

from constants import TEXT_FONT


# Math
def increment_no_wrap(index: int, max: int) -> int:
    if index + 1 <= max:
        return index + 1
    return index


def decrement_no_wrap(index: int) -> int:
    if index - 1 <= 0:
        return 0
    return index - 1


def increment_with_wrap(index: int, max: int) -> int:
    if index + 1 > max:
        return 0
    return index + 1


def decrement_with_wrap(index: int, max: int) -> int:
    if index - 1 < 0:
        return max
    return index - 1


# Music management
def scan_local_music():
    subprocess.run(["mopidy", "local", "scan"], check=True)


# UI/UX
def str_to_pixel_count(string: str) -> int:
    # uses pil and imagedraw to get the width of text in pixels
    font = TEXT_FONT
    draw = ImageDraw.Draw(Image.new("RGB", (0, 0)))
    left, _, right, _ = draw.textbbox((0, 0), string, font=font)
    return right - left
