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
    """Create a centered four-color test image."""
    if width <= 0 or height <= 0:
        raise ValueError(
            "Panel width and height must be greater than zero"
        )

    image = Image.new(
        mode="RGB",
        size=(width, height),
        color=(0, 0, 0),
    )
    draw = ImageDraw.Draw(image)

    center_x = width // 2
    center_y = height // 2

    draw.rectangle(
        (0, 0, center_x - 1, center_y - 1),
        fill=(255, 0, 0),
    )
    draw.rectangle(
        (center_x, 0, width - 1, center_y - 1),
        fill=(0, 255, 0),
    )
    draw.rectangle(
        (0, center_y, center_x - 1, height - 1),
        fill=(0, 0, 255),
    )
    draw.rectangle(
        (center_x, center_y, width - 1, height - 1),
        fill=(255, 255, 255),
    )

    cross_width = 2

    vertical_start = (width - cross_width) // 2
    vertical_end = vertical_start + cross_width - 1

    horizontal_start = (height - cross_width) // 2
    horizontal_end = horizontal_start + cross_width - 1

    draw.rectangle(
        (0, horizontal_start, width - 1, horizontal_end),
        fill=(255, 255, 0),
    )
    draw.rectangle(
        (vertical_start, 0, vertical_end, height - 1),
        fill=(255, 255, 0),
    )

    buffer = BytesIO()
    image.save(
        buffer,
        format="PNG",
        optimize=False,
    )

    return buffer.getvalue()
