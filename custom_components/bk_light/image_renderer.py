"""Static image rendering for BK-Light LED matrices."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError

FitMode = Literal["contain", "cover", "stretch"]
ResamplingMode = Literal["nearest", "lanczos"]
RgbColor = tuple[int, int, int]

SUPPORTED_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".webp",
}


class ImagePathError(ValueError):
    """Raised when an image path is invalid."""


def render_image_file(
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
) -> bytes:
    """Render a legacy relative image path below a safe base directory."""
    image_path = _resolve_image_path(
        base_directory=base_directory,
        requested_path=requested_path,
    )
    return render_image_path(
        str(image_path),
        width,
        height,
        fit,
        background_color,
        rotation,
        mirror_horizontal,
        mirror_vertical,
        brightness,
        resampling,
    )


def render_image_path(
    image_path: str,
    width: int,
    height: int,
    fit: FitMode,
    background_color: RgbColor,
    rotation: int,
    mirror_horizontal: bool,
    mirror_vertical: bool,
    brightness: float,
    resampling: ResamplingMode,
) -> bytes:
    """Load, transform, resize and encode a local image path."""
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

    path = Path(image_path).resolve()

    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {path}")

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(
            f"Unsupported image format {path.suffix!r}; "
            f"supported formats: {supported}"
        )

    try:
        with Image.open(path) as source:
            if getattr(source, "is_animated", False):
                source.seek(0)
            image = ImageOps.exif_transpose(source).convert("RGBA")
    except UnidentifiedImageError as err:
        raise ValueError(
            f"The file is not a supported image: {path.name}"
        ) from err

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

    resized = _resize_image(
        image=image,
        width=width,
        height=height,
        fit=fit,
        background_color=background_color,
        resampling=resampling,
    )

    output = BytesIO()
    resized.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _resolve_image_path(
    base_directory: str,
    requested_path: str,
) -> Path:
    """Resolve a safe legacy path below the BK-Light web directory."""
    raw_path = requested_path.strip()

    if not raw_path:
        raise ImagePathError("Image path must not be empty")

    relative_path = Path(raw_path)

    if relative_path.is_absolute():
        raise ImagePathError(
            "Use a relative path below /config/www/bk_light"
        )

    base_path = Path(base_directory).resolve()
    image_path = (base_path / relative_path).resolve()

    if not image_path.is_relative_to(base_path):
        raise ImagePathError(
            "The image path must remain below /config/www/bk_light"
        )

    if not image_path.exists():
        image_path = _resolve_case_insensitive(
            base_path=base_path,
            relative_path=relative_path,
        )

    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {requested_path}")

    return image_path


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
            raise ImagePathError("Parent-directory traversal is not allowed")

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
        raise ImagePathError(
            "The image path must remain below /config/www/bk_light"
        )

    return resolved


def _resize_image(
    image: Image.Image,
    width: int,
    height: int,
    fit: FitMode,
    background_color: RgbColor,
    resampling: ResamplingMode,
) -> Image.Image:
    """Resize and composite an RGBA image onto an RGB panel canvas."""
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


def _validate_color(color: RgbColor) -> None:
    """Validate an RGB color."""
    if len(color) != 3:
        raise ValueError("RGB colors must contain exactly three values")
    if any(channel < 0 or channel > 255 for channel in color):
        raise ValueError("RGB values must be between 0 and 255")
