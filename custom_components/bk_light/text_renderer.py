"""Text rendering for BK-Light LED matrices."""

from __future__ import annotations

from io import BytesIO
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

HorizontalAlign = Literal["left", "center", "right"]
VerticalAlign = Literal["top", "center", "bottom"]
ScrollDirection = Literal["left", "right"]
RgbColor = tuple[int, int, int]

MIN_FONT_SIZE = 5
DEFAULT_MARGIN = 1


def render_text_png(
    text: str,
    width: int,
    height: int,
    text_color: RgbColor,
    background_color: RgbColor,
    font_size: int,
    auto_fit: bool,
    horizontal_align: HorizontalAlign,
    vertical_align: VerticalAlign,
    x_offset: int = 0,
    y_offset: int = 0,
) -> bytes:
    """Render static text to a panel-sized PNG."""
    _validate_common(
        text=text,
        width=width,
        height=height,
        text_color=text_color,
        background_color=background_color,
    )

    image = Image.new("RGB", (width, height), background_color)
    draw = ImageDraw.Draw(image)

    font = _get_static_font(
        draw=draw,
        text=text,
        width=width,
        height=height,
        requested_size=font_size,
        auto_fit=auto_fit,
        horizontal_align=horizontal_align,
    )

    left, top, right, bottom = draw.multiline_textbbox(
        (0, 0),
        text,
        font=font,
        spacing=0,
        align=horizontal_align,
    )

    rendered_width = right - left
    rendered_height = bottom - top

    x = _horizontal_position(
        panel_width=width,
        content_width=rendered_width,
        alignment=horizontal_align,
    )
    y = _vertical_position(
        panel_height=height,
        content_height=rendered_height,
        alignment=vertical_align,
    )

    draw.multiline_text(
        (x - left + x_offset, y - top + y_offset),
        text,
        font=font,
        fill=text_color,
        spacing=0,
        align=horizontal_align,
    )

    return _encode_png(image)


def render_scroll_frames(
    text: str,
    width: int,
    height: int,
    text_color: RgbColor,
    background_color: RgbColor,
    font_size: int,
    auto_fit: bool,
    vertical_align: VerticalAlign,
    direction: ScrollDirection,
    step: int,
    gap: int,
    y_offset: int = 0,
) -> list[bytes]:
    """Render all frames for horizontal scrolling text."""
    text = " ".join(text.splitlines()).strip()

    _validate_common(
        text=text,
        width=width,
        height=height,
        text_color=text_color,
        background_color=background_color,
    )

    if direction not in ("left", "right"):
        raise ValueError("Direction must be left or right")
    if step <= 0:
        raise ValueError("Step must be greater than zero")
    if gap < 0:
        raise ValueError("Gap must not be negative")

    measuring_image = Image.new("RGB", (width, height), background_color)
    measuring_draw = ImageDraw.Draw(measuring_image)

    font = _get_scroll_font(
        draw=measuring_draw,
        text=text,
        height=height,
        requested_size=font_size,
        auto_fit=auto_fit,
    )

    left, top, right, bottom = measuring_draw.textbbox(
        (0, 0),
        text,
        font=font,
    )
    text_width = max(1, right - left)
    text_height = max(1, bottom - top)

    y = _vertical_position(
        panel_height=height,
        content_height=text_height,
        alignment=vertical_align,
    )

    positions = _scroll_positions(
        panel_width=width,
        text_width=text_width,
        direction=direction,
        step=step,
        gap=gap,
    )

    frames: list[bytes] = []

    for x in positions:
        image = Image.new("RGB", (width, height), background_color)
        draw = ImageDraw.Draw(image)
        draw.text(
            (x - left, y - top + y_offset),
            text,
            font=font,
            fill=text_color,
        )
        frames.append(_encode_png(image))

    return frames


def _scroll_positions(
    panel_width: int,
    text_width: int,
    direction: ScrollDirection,
    step: int,
    gap: int,
) -> list[int]:
    """Calculate horizontal positions for one scroll pass."""
    if direction == "left":
        start = panel_width
        end = -text_width - gap
        positions = list(range(start, end - 1, -step))
        if not positions or positions[-1] != end:
            positions.append(end)
        return positions

    start = -text_width
    end = panel_width + gap
    positions = list(range(start, end + 1, step))
    if not positions or positions[-1] != end:
        positions.append(end)
    return positions


def _get_static_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    width: int,
    height: int,
    requested_size: int,
    auto_fit: bool,
    horizontal_align: HorizontalAlign,
) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Load a font and optionally fit width and height."""
    size = max(MIN_FONT_SIZE, requested_size)

    while True:
        font = _load_font(size)
        left, top, right, bottom = draw.multiline_textbbox(
            (0, 0),
            text,
            font=font,
            spacing=0,
            align=horizontal_align,
        )
        rendered_width = right - left
        rendered_height = bottom - top

        fits_width = rendered_width <= width - (DEFAULT_MARGIN * 2)
        fits_height = rendered_height <= height - (DEFAULT_MARGIN * 2)

        if not auto_fit or (fits_width and fits_height) or size <= MIN_FONT_SIZE:
            return font

        size -= 1


def _get_scroll_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    height: int,
    requested_size: int,
    auto_fit: bool,
) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Load a scrolling font and fit only its height."""
    size = max(MIN_FONT_SIZE, requested_size)

    while True:
        font = _load_font(size)
        _left, top, _right, bottom = draw.textbbox(
            (0, 0),
            text,
            font=font,
        )
        rendered_height = bottom - top
        fits_height = rendered_height <= height - (DEFAULT_MARGIN * 2)

        if not auto_fit or fits_height or size <= MIN_FONT_SIZE:
            return font

        size -= 1


def _load_font(
    size: int,
) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Load a suitable font with fallbacks."""
    for font_name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(font_name, size=size)
        except OSError:
            continue

    return ImageFont.load_default()


def _horizontal_position(
    panel_width: int,
    content_width: int,
    alignment: HorizontalAlign,
) -> int:
    """Calculate horizontal text position."""
    if alignment == "left":
        return DEFAULT_MARGIN
    if alignment == "right":
        return panel_width - content_width - DEFAULT_MARGIN
    return (panel_width - content_width) // 2


def _vertical_position(
    panel_height: int,
    content_height: int,
    alignment: VerticalAlign,
) -> int:
    """Calculate vertical text position."""
    if alignment == "top":
        return DEFAULT_MARGIN
    if alignment == "bottom":
        return panel_height - content_height - DEFAULT_MARGIN
    return (panel_height - content_height) // 2


def _validate_common(
    text: str,
    width: int,
    height: int,
    text_color: RgbColor,
    background_color: RgbColor,
) -> None:
    """Validate common text-rendering arguments."""
    if not text.strip():
        raise ValueError("Text must not be empty")
    if width <= 0 or height <= 0:
        raise ValueError("Panel dimensions must be greater than zero")

    _validate_color(text_color)
    _validate_color(background_color)


def _validate_color(color: RgbColor) -> None:
    """Validate an RGB color."""
    if len(color) != 3:
        raise ValueError("RGB colors must contain exactly three values")
    if any(channel < 0 or channel > 255 for channel in color):
        raise ValueError("RGB values must be between 0 and 255")


def _encode_png(image: Image.Image) -> bytes:
    """Encode an image as PNG."""
    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()
