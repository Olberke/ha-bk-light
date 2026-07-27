"""Button entities for the BK-Light integration."""

from __future__ import annotations

from io import BytesIO
import logging

from PIL import Image, ImageDraw

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PANEL_HEIGHT, PANEL_WIDTH
from .display_session import BkLightError
from .runtime import BkLightRuntimeData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BK-Light button entities."""
    runtime = entry.runtime_data

    if not isinstance(runtime, BkLightRuntimeData):
        raise RuntimeError("BK-Light runtime data is not available")

    async_add_entities(
        [
            BkLightTestImageButton(
                runtime=runtime,
                device_name=entry.title,
            )
        ]
    )


class BkLightTestImageButton(ButtonEntity):
    """Send a generated color test image to the panel."""

    _attr_has_entity_name = True
    _attr_name = "Testbild senden"
    _attr_icon = "mdi:image-sync"

    def __init__(
        self,
        runtime: BkLightRuntimeData,
        device_name: str,
    ) -> None:
        """Initialize the test-image button."""
        self._runtime = runtime
        self._device_name = device_name

        address = runtime.session.address

        self._attr_unique_id = f"{address}_send_test_image"

        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(dr.CONNECTION_BLUETOOTH, address)},
            name=device_name,
            manufacturer="BK-Light",
            model=f"RGB LED Matrix {PANEL_WIDTH}x{PANEL_HEIGHT}",
        )

    async def async_press(self) -> None:
        """Generate and send a centered test image."""
        try:
            png_bytes = await self.hass.async_add_executor_job(
                create_test_image,
                PANEL_WIDTH,
                PANEL_HEIGHT,
            )

            await self._runtime.async_stop_animation()

            await self._runtime.session.send_png(
                png_bytes,
                delay=0.2,
            )

            _LOGGER.debug(
                "Test image successfully sent to %s",
                self._device_name,
            )

        except BkLightError as err:
            _LOGGER.exception(
                "BK-Light protocol error for %s",
                self._device_name,
            )

            raise HomeAssistantError(
                f"Das Testbild konnte nicht übertragen werden: {err}"
            ) from err

        except (OSError, RuntimeError, ValueError) as err:
            _LOGGER.exception(
                "Could not send test image to %s",
                self._device_name,
            )

            raise HomeAssistantError(
                f"Fehler beim Senden des Testbilds: {err}"
            ) from err


def create_test_image(
    width: int,
    height: int,
) -> bytes:
    """Create a BK-Light pulse test image."""
    if width <= 0 or height <= 0:
        raise ValueError(
            "Panel width and height must be greater than zero"
        )

    image = Image.new(
        mode="RGB",
        size=(width, height),
        color=(5, 7, 16),
    )
    draw = ImageDraw.Draw(image)

    center_x = width // 2
    center_y = height // 2

    # Skalierung für unterschiedliche Panelgrößen.
    max_radius = max(2, min(width, height) // 2 - 2)

    # Äußere, rautenförmige Signalringe.
    ring_colors = (
        (20, 85, 135),
        (30, 150, 165),
        (120, 55, 190),
    )

    ring_radii = (
        max_radius,
        max(2, max_radius - 3),
        max(2, max_radius - 6),
    )

    for radius, color in zip(
        ring_radii,
        ring_colors,
        strict=True,
    ):
        points = [
            (center_x, center_y - radius),
            (center_x + radius, center_y),
            (center_x, center_y + radius),
            (center_x - radius, center_y),
            (center_x, center_y - radius),
        ]
        draw.line(
            points,
            fill=color,
            width=1,
        )

    # Innerer leuchtender Diamant.
    outer_core_radius = max(2, min(width, height) // 6)
    inner_core_radius = max(1, outer_core_radius - 2)

    draw.polygon(
        [
            (center_x, center_y - outer_core_radius),
            (center_x + outer_core_radius, center_y),
            (center_x, center_y + outer_core_radius),
            (center_x - outer_core_radius, center_y),
        ],
        fill=(215, 55, 155),
    )

    draw.polygon(
        [
            (center_x, center_y - inner_core_radius),
            (center_x + inner_core_radius, center_y),
            (center_x, center_y + inner_core_radius),
            (center_x - inner_core_radius, center_y),
        ],
        fill=(255, 145, 45),
    )

    # Heller Mittelpunkt.
    draw.point(
        (center_x, center_y),
        fill=(255, 255, 255),
    )

    if center_x > 0:
        draw.point(
            (center_x - 1, center_y),
            fill=(255, 235, 170),
        )

    if center_x + 1 < width:
        draw.point(
            (center_x + 1, center_y),
            fill=(255, 235, 170),
        )

    if center_y > 0:
        draw.point(
            (center_x, center_y - 1),
            fill=(255, 235, 170),
        )

    if center_y + 1 < height:
        draw.point(
            (center_x, center_y + 1),
            fill=(255, 235, 170),
        )

    # Kleine Testpunkte zur Kontrolle einzelner Farben und Pixel.
    accent_pixels = (
        (
            center_x - max_radius // 2,
            center_y - max_radius // 3,
            (35, 220, 190),
        ),
        (
            center_x + max_radius // 2,
            center_y + max_radius // 3,
            (180, 75, 230),
        ),
        (
            center_x - max_radius // 3,
            center_y + max_radius // 2,
            (255, 90, 70),
        ),
        (
            center_x + max_radius // 3,
            center_y - max_radius // 2,
            (255, 185, 55),
        ),
    )

    for x, y, color in accent_pixels:
        if 0 <= x < width and 0 <= y < height:
            draw.point(
                (x, y),
                fill=color,
            )

    buffer = BytesIO()
    image.save(
        buffer,
        format="PNG",
        optimize=False,
    )

    return buffer.getvalue()
