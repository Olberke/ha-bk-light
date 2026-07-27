"""Helpers for Home Assistant media selections."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.components import media_source
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

MEDIA_CONTENT_ID = "media_content_id"


async def async_resolve_local_media_path(
    hass: HomeAssistant,
    selection: dict[str, Any],
) -> Path:
    """Resolve a media-selector result to a local filesystem path."""
    media_content_id = selection.get(MEDIA_CONTENT_ID)

    if not isinstance(media_content_id, str) or not media_content_id:
        raise ServiceValidationError(
            "Die Medienauswahl enthält keine gültige Medien-ID"
        )

    if not media_source.is_media_source_id(media_content_id):
        raise ServiceValidationError(
            "Es werden nur Home-Assistant-Medienquellen unterstützt"
        )

    try:
        resolved = await media_source.async_resolve_media(
            hass,
            media_content_id,
        )
    except Exception as err:
        raise ServiceValidationError(
            f"Die ausgewählte Mediendatei konnte nicht aufgelöst werden: {err}"
        ) from err

    if resolved.path is None:
        raise ServiceValidationError(
            "Die ausgewählte Medienquelle ist keine lokale Datei. "
            "Wähle eine Datei aus Lokale Medien."
        )

    path = Path(resolved.path).resolve()

    if not path.is_file():
        raise ServiceValidationError(
            f"Die ausgewählte Mediendatei wurde nicht gefunden: {path}"
        )

    return path
