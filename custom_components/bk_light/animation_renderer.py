"""Animated image rendering for BK-Light LED matrices."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError

FitMode = Literal["contain", "cover", "stretch"]
ResamplingMode = Literal["nearest", "lanczos"]
RgbColor = tuple[int, int, int]

MAX_SOURCE_FRAMES = 1000
MAX_OUTPUT_FRAMES = 400
DEFAULT_FRAME_DURATION_MS = 100
MIN_FRAME_DURATION_MS = 20


class AnimationPathError(ValueError):
    """Raised when an animation path is invalid."""


def render_gif_file(
    base_directory: str,
    requested_path: str,
    width: int,
    height: int,
    fit: FitMode,
    background_color: RgbColor,
    rotation: int,
    mirror_horizontal: bool,
    mirror_vertical: bool,
    brightness: float,
    resampling: ResamplingMode,
    speed: float,
    max_fps: float,
) -> tuple[tuple[bytes, ...], tuple[float, ...]]:
    """Render a legacy relative GIF path below a safe base directory."""
    animation_path = _resolve_animation_path(
        base_directory=base_directory,
        requested_path=requested_path,
    )
    return render_gif_path(
        str(animation_path),
        width,
        height,
        fit,
        background_color,
        rotation,
        mirror_horizontal,
        mirror_vertical,
        brightness,
        resampling,
        speed,
        max_fps,
    )


def render_gif_path(
    animation_path: str,
    width: int,
    height: int,
    fit: FitMode,
    background_color: RgbColor,
    rotation: int,
    mirror_horizontal: bool,
    mirror_vertical: bool,
    brightness: float,
    resampling: ResamplingMode,
    speed: float,
    max_fps: float,
) -> tuple[tuple[bytes, ...], tuple[float, ...]]:
    """Load a local GIF and return panel-sized PNG frames and durations."""
    if width <= 0 or height <= 0:
        raise ValueError("Panel dimensions must be greater than zero")

    _validate_color(background_color)

    if fit not in ("contain", "cover", "stretch"):
        raise ValueError("Fit must be contain, cover or stretch")
    if rotation not in (0, 90, 180, 270):
        raise ValueError("Rotation must be 0, 90, 180 or 270 degrees")
    if brightness <= 0 or brightness > 2.0:
        raise ValueError("Brightness must be greater than 0 and at most 2.0")
    if resampling not in ("nearest", "lanczos"):
        raise ValueError("Resampling must be nearest or lanczos")
    if speed <= 0 or speed > 4.0:
        raise ValueError("Speed must be greater than 0 and at most 4.0")
    if max_fps < 1.0 or max_fps > 12.0:
        raise ValueError("Max FPS must be between 1 and 12")

    path = Path(animation_path).resolve()

    if not path.is_file():
        raise FileNotFoundError(f"Animation not found: {path}")
    if path.suffix.lower() != ".gif":
        raise ValueError("Only GIF files are supported by play_gif")

    min_output_duration = 1.0 / max_fps
    output_frames: list[bytes] = []
    output_durations: list[float] = []

    pending_png: bytes | None = None
    pending_duration = 0.0

    try:
        with Image.open(path) as source:
            if not getattr(source, "is_animated", False):
                raise ValueError(
                    f"The GIF contains only one frame: {path.name}"
                )

            frame_count = int(getattr(source, "n_frames", 1))
            if frame_count > MAX_SOURCE_FRAMES:
                raise ValueError(
                    f"GIF contains {frame_count} frames; "
                    f"the limit is {MAX_SOURCE_FRAMES}"
                )

            for frame_index in range(frame_count):
                source.seek(frame_index)

                duration_ms = int(
                    source.info.get(
                        "duration",
                        DEFAULT_FRAME_DURATION_MS,
                    )
                    or DEFAULT_FRAME_DURATION_MS
                )
                duration_ms = max(MIN_FRAME_DURATION_MS, duration_ms)
                duration_seconds = (duration_ms / 1000.0) / speed

                frame = source.convert("RGBA")
                frame = _transform_frame(
                    image=frame,
                    width=width,
                    height=height,
                    fit=fit,
                    background_color=background_color,
                    rotation=rotation,
                    mirror_horizontal=mirror_horizontal,
                    mirror_vertical=mirror_vertical,
                    brightness=brightness,
                    resampling=resampling,
                )
                png_bytes = _encode_png(frame)

                pending_png = png_bytes
                pending_duration += duration_seconds

                if pending_duration < min_output_duration:
                    continue

                _append_or_merge(
                    frames=output_frames,
                    durations=output_durations,
                    png_bytes=pending_png,
                    duration=pending_duration,
                )
                pending_png = None
                pending_duration = 0.0

            if pending_png is not None and pending_duration > 0:
                _append_or_merge(
                    frames=output_frames,
                    durations=output_durations,
                    png_bytes=pending_png,
                    duration=pending_duration,
                )

    except UnidentifiedImageError as err:
        raise ValueError(
            f"The file is not a supported GIF: {path.name}"
        ) from err

    if not output_frames:
        raise ValueError("The GIF produced no usable animation frames")
    if len(output_frames) > MAX_OUTPUT_FRAMES:
        raise ValueError(
            f"The prepared animation contains {len(output_frames)} frames; "
            f"the limit is {MAX_OUTPUT_FRAMES}"
        )

    return tuple(output_frames), tuple(output_durations)


def _append_or_merge(
    *,
    frames: list[bytes],
    durations: list[float],
    png_bytes: bytes,
    duration: float,
) -> None:
    """Append a frame or merge its duration with an identical predecessor."""
    if frames and frames[-1] == png_bytes:
        durations[-1] += duration
        return

    frames.append(png_bytes)
    durations.append(duration)


def _resolve_animation_path(
    base_directory: str,
    requested_path: str,
) -> Path:
    """Resolve a safe legacy GIF path below the BK-Light web directory."""
    raw_path = requested_path.strip()

    if not raw_path:
        raise AnimationPathError("Animation path must not be empty")

    relative_path = Path(raw_path)

    if relative_path.is_absolute():
        raise AnimationPathError(
            "Use a relative path below /config/www/bk_light"
        )

    base_path = Path(base_directory).resolve()
    animation_path = (base_path / relative_path).resolve()

    if not animation_path.is_relative_to(base_path):
        raise AnimationPathError(
            "The animation path must remain below /config/www/bk_light"
        )

    if not animation_path.exists():
        animation_path = _resolve_case_insensitive(
            base_path=base_path,
            relative_path=relative_path,
        )

    if not animation_path.is_file():
        raise FileNotFoundError(f"Animation not found: {requested_path}")

    return animation_path


def _resolve_case_insensitive(
    *,
    base_path: Path,
    relative_path: Path,
) -> Path:
    """Resolve path components case-insensitively below base_path."""
    current = base_path

    for component in relative_path.parts:
        if component in ("", "."):
            continue
        if component == "..":
            raise AnimationPathError(
                "Parent-directory traversal is not allowed"
            )

        try:
            matches = [
                child
                for child in current.iterdir()
                if child.name.casefold() == component.casefold()
            ]
        except FileNotFoundError:
            return current / component

        if len(matches) != 1:
            return current / component

        current = matches[0]

    resolved = current.resolve()

    if not resolved.is_relative_to(base_path):
        raise AnimationPathError(
            "The animation path must remain below /config/www/bk_light"
        )

    return resolved


def _transform_frame(
    *,
    image: Image.Image,
    width: int,
    height: int,
    fit: FitMode,
    background_color: RgbColor,
    rotation: int,
    mirror_horizontal: bool,
    mirror_vertical: bool,
    brightness: float,
    resampling: ResamplingMode,
) -> Image.Image:
    """Transform one GIF frame into a panel-sized RGB image."""
    if rotation:
        image = image.rotate(
            -rotation,
            expand=True,
            resample=Image.Resampling.NEAREST,
        )
    if mirror_horizontal:
        image = ImageOps.mirror(image)
    if mirror_vertical:
        image = ImageOps.flip(image)
    if brightness != 1.0:
        image = ImageEnhance.Brightness(image).enhance(brightness)

    resample_filter = (
        Image.Resampling.NEAREST
        if resampling == "nearest"
        else Image.Resampling.LANCZOS
    )

    if fit == "stretch":
        transformed = image.resize(
            (width, height),
            resample=resample_filter,
        )
    elif fit == "cover":
        transformed = ImageOps.fit(
            image,
            (width, height),
            method=resample_filter,
            centering=(0.5, 0.5),
        )
    else:
        transformed = image.copy()
        transformed.thumbnail(
            (width, height),
            resample=resample_filter,
        )
        contained = Image.new(
            "RGBA",
            (width, height),
            (*background_color, 255),
        )
        x = (width - transformed.width) // 2
        y = (height - transformed.height) // 2
        contained.alpha_composite(transformed, dest=(x, y))
        transformed = contained

    background = Image.new(
        "RGBA",
        (width, height),
        (*background_color, 255),
    )
    background.alpha_composite(transformed)
    return background.convert("RGB")


def _encode_png(image: Image.Image) -> bytes:
    """Encode one frame as PNG."""
    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _validate_color(color: RgbColor) -> None:
    """Validate an RGB color."""
    if len(color) != 3:
        raise ValueError("RGB colors must contain exactly three values")
    if any(channel < 0 or channel > 255 for channel in color):
        raise ValueError("RGB values must be between 0 and 255")
