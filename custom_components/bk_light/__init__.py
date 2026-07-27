"""BK-Light LED Matrix integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .animation_renderer import (
    AnimationPathError,
    render_gif_file,
    render_gif_path,
)
from .const import (
    ATTR_AUTO_FIT,
    ATTR_BACKGROUND_COLOR,
    ATTR_BRIGHTNESS,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DIRECTION,
    ATTR_FIT,
    ATTR_FONT_SIZE,
    ATTR_FPS,
    ATTR_GAP,
    ATTR_HORIZONTAL_ALIGN,
    ATTR_MAX_FPS,
    ATTR_MEDIA,
    ATTR_MIRROR_HORIZONTAL,
    ATTR_MIRROR_VERTICAL,
    ATTR_PATH,
    ATTR_REPEAT,
    ATTR_RESAMPLING,
    ATTR_ROTATION,
    ATTR_SPEED,
    ATTR_STEP,
    ATTR_TEXT,
    ATTR_TEXT_COLOR,
    ATTR_VERTICAL_ALIGN,
    ATTR_X_OFFSET,
    ATTR_Y_OFFSET,
    DEFAULT_AUTO_FIT,
    DEFAULT_BACKGROUND_COLOR,
    DEFAULT_FONT_SIZE,
    DEFAULT_GIF_MAX_FPS,
    DEFAULT_GIF_SPEED,
    DEFAULT_HORIZONTAL_ALIGN,
    DEFAULT_IMAGE_BRIGHTNESS,
    DEFAULT_IMAGE_FIT,
    DEFAULT_IMAGE_ROTATION,
    DEFAULT_MIRROR_HORIZONTAL,
    DEFAULT_MIRROR_VERTICAL,
    DEFAULT_RESAMPLING,
    DEFAULT_SCROLL_DIRECTION,
    DEFAULT_SCROLL_FPS,
    DEFAULT_SCROLL_GAP,
    DEFAULT_SCROLL_REPEAT,
    DEFAULT_SCROLL_STEP,
    DEFAULT_TEXT_COLOR,
    DEFAULT_VERTICAL_ALIGN,
    DOMAIN,
    PANEL_HEIGHT,
    PANEL_WIDTH,
    SERVICE_DISPLAY_IMAGE,
    SERVICE_DISPLAY_TEXT,
    SERVICE_PLAY_GIF,
    SERVICE_SCROLL_TEXT,
    SERVICE_STOP_ANIMATION,
)
from .display_session import BkLightError, BleDisplaySession
from .image_renderer import (
    ImagePathError,
    render_image_file,
    render_image_path,
)
from .media_helper import async_resolve_local_media_path
from .runtime import BkLightRuntimeData
from .text_renderer import render_scroll_frames, render_text_png

_LOGGER = logging.getLogger(__name__)

PLATFORMS: tuple[Platform, ...] = (Platform.BUTTON,)

RGB_COLOR_SCHEMA = vol.All(
    [
        vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=255),
        )
    ],
    vol.Length(min=3, max=3),
)

MEDIA_SELECTION_SCHEMA = vol.Schema(
    {
        vol.Required("media_content_id"): cv.string,
        vol.Optional("media_content_type"): cv.string,
        vol.Optional("metadata"): dict,
    },
    extra=vol.ALLOW_EXTRA,
)


def _require_media_or_path(data: dict[str, Any]) -> dict[str, Any]:
    """Require a UI media selection or a legacy path."""
    if not data.get(ATTR_MEDIA) and not data.get(ATTR_PATH):
        raise vol.Invalid(
            "Eine Mediendatei muss ausgewählt werden"
        )
    return data


DISPLAY_TEXT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_TEXT): vol.All(
            cv.string,
            vol.Length(min=1, max=250),
        ),
        vol.Optional(
            ATTR_TEXT_COLOR,
            default=list(DEFAULT_TEXT_COLOR),
        ): RGB_COLOR_SCHEMA,
        vol.Optional(
            ATTR_BACKGROUND_COLOR,
            default=list(DEFAULT_BACKGROUND_COLOR),
        ): RGB_COLOR_SCHEMA,
        vol.Optional(
            ATTR_FONT_SIZE,
            default=DEFAULT_FONT_SIZE,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=5, max=64),
        ),
        vol.Optional(
            ATTR_AUTO_FIT,
            default=DEFAULT_AUTO_FIT,
        ): cv.boolean,
        vol.Optional(
            ATTR_HORIZONTAL_ALIGN,
            default=DEFAULT_HORIZONTAL_ALIGN,
        ): vol.In(("left", "center", "right")),
        vol.Optional(
            ATTR_VERTICAL_ALIGN,
            default=DEFAULT_VERTICAL_ALIGN,
        ): vol.In(("top", "center", "bottom")),
        vol.Optional(
            ATTR_X_OFFSET,
            default=0,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=-32, max=32),
        ),
        vol.Optional(
            ATTR_Y_OFFSET,
            default=0,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=-32, max=32),
        ),
    }
)

SCROLL_TEXT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_TEXT): vol.All(
            cv.string,
            vol.Length(min=1, max=250),
        ),
        vol.Optional(
            ATTR_TEXT_COLOR,
            default=list(DEFAULT_TEXT_COLOR),
        ): RGB_COLOR_SCHEMA,
        vol.Optional(
            ATTR_BACKGROUND_COLOR,
            default=list(DEFAULT_BACKGROUND_COLOR),
        ): RGB_COLOR_SCHEMA,
        vol.Optional(
            ATTR_FONT_SIZE,
            default=DEFAULT_FONT_SIZE,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=5, max=64),
        ),
        vol.Optional(
            ATTR_AUTO_FIT,
            default=DEFAULT_AUTO_FIT,
        ): cv.boolean,
        vol.Optional(
            ATTR_VERTICAL_ALIGN,
            default=DEFAULT_VERTICAL_ALIGN,
        ): vol.In(("top", "center", "bottom")),
        vol.Optional(
            ATTR_DIRECTION,
            default=DEFAULT_SCROLL_DIRECTION,
        ): vol.In(("left", "right")),
        vol.Optional(
            ATTR_FPS,
            default=DEFAULT_SCROLL_FPS,
        ): vol.All(
            vol.Coerce(float),
            vol.Range(min=1.0, max=12.0),
        ),
        vol.Optional(
            ATTR_STEP,
            default=DEFAULT_SCROLL_STEP,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=8),
        ),
        vol.Optional(
            ATTR_GAP,
            default=DEFAULT_SCROLL_GAP,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=64),
        ),
        vol.Optional(
            ATTR_REPEAT,
            default=DEFAULT_SCROLL_REPEAT,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=100),
        ),
        vol.Optional(
            ATTR_Y_OFFSET,
            default=0,
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=-32, max=32),
        ),
    }
)

STOP_ANIMATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
    }
)

DISPLAY_IMAGE_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
            vol.Optional(ATTR_MEDIA): MEDIA_SELECTION_SCHEMA,
            vol.Optional(ATTR_PATH): vol.All(
                cv.string,
                vol.Length(min=1, max=500),
            ),
            vol.Optional(
                ATTR_FIT,
                default=DEFAULT_IMAGE_FIT,
            ): vol.In(("contain", "cover", "stretch")),
            vol.Optional(
                ATTR_BACKGROUND_COLOR,
                default=list(DEFAULT_BACKGROUND_COLOR),
            ): RGB_COLOR_SCHEMA,
            vol.Optional(
                ATTR_ROTATION,
                default=DEFAULT_IMAGE_ROTATION,
            ): vol.All(
                vol.Coerce(int),
                vol.In((0, 90, 180, 270)),
            ),
            vol.Optional(
                ATTR_MIRROR_HORIZONTAL,
                default=DEFAULT_MIRROR_HORIZONTAL,
            ): cv.boolean,
            vol.Optional(
                ATTR_MIRROR_VERTICAL,
                default=DEFAULT_MIRROR_VERTICAL,
            ): cv.boolean,
            vol.Optional(
                ATTR_BRIGHTNESS,
                default=DEFAULT_IMAGE_BRIGHTNESS,
            ): vol.All(
                vol.Coerce(float),
                vol.Range(min=0.05, max=2.0),
            ),
            vol.Optional(
                ATTR_RESAMPLING,
                default=DEFAULT_RESAMPLING,
            ): vol.In(("nearest", "lanczos")),
        }
    ),
    _require_media_or_path,
)

PLAY_GIF_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
            vol.Optional(ATTR_MEDIA): MEDIA_SELECTION_SCHEMA,
            vol.Optional(ATTR_PATH): vol.All(
                cv.string,
                vol.Length(min=1, max=500),
            ),
            vol.Optional(
                ATTR_FIT,
                default=DEFAULT_IMAGE_FIT,
            ): vol.In(("contain", "cover", "stretch")),
            vol.Optional(
                ATTR_BACKGROUND_COLOR,
                default=list(DEFAULT_BACKGROUND_COLOR),
            ): RGB_COLOR_SCHEMA,
            vol.Optional(
                ATTR_ROTATION,
                default=DEFAULT_IMAGE_ROTATION,
            ): vol.All(
                vol.Coerce(int),
                vol.In((0, 90, 180, 270)),
            ),
            vol.Optional(
                ATTR_MIRROR_HORIZONTAL,
                default=DEFAULT_MIRROR_HORIZONTAL,
            ): cv.boolean,
            vol.Optional(
                ATTR_MIRROR_VERTICAL,
                default=DEFAULT_MIRROR_VERTICAL,
            ): cv.boolean,
            vol.Optional(
                ATTR_BRIGHTNESS,
                default=DEFAULT_IMAGE_BRIGHTNESS,
            ): vol.All(
                vol.Coerce(float),
                vol.Range(min=0.05, max=2.0),
            ),
            vol.Optional(
                ATTR_RESAMPLING,
                default="nearest",
            ): vol.In(("nearest", "lanczos")),
            vol.Optional(
                ATTR_SPEED,
                default=DEFAULT_GIF_SPEED,
            ): vol.All(
                vol.Coerce(float),
                vol.Range(min=0.25, max=4.0),
            ),
            vol.Optional(
                ATTR_MAX_FPS,
                default=DEFAULT_GIF_MAX_FPS,
            ): vol.All(
                vol.Coerce(float),
                vol.Range(min=1.0, max=12.0),
            ),
            vol.Optional(
                ATTR_REPEAT,
                default=DEFAULT_SCROLL_REPEAT,
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=0, max=100),
            ),
        }
    ),
    _require_media_or_path,
)


def _get_runtime(
    hass: HomeAssistant,
    entry_id: str,
) -> tuple[ConfigEntry, BkLightRuntimeData]:
    """Return a loaded BK-Light entry and its runtime data."""
    entry = hass.config_entries.async_get_entry(entry_id)

    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            "Der ausgewählte BK-Light-Eintrag wurde nicht gefunden"
        )

    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            "Der ausgewählte BK-Light-Eintrag ist nicht geladen"
        )

    runtime = entry.runtime_data

    if not isinstance(runtime, BkLightRuntimeData):
        raise HomeAssistantError(
            "Die BK-Light-Laufzeitdaten sind nicht verfügbar"
        )

    return entry, runtime


def _rgb_color(
    value: list[int] | tuple[int, ...],
) -> tuple[int, int, int]:
    """Convert a validated RGB sequence into a tuple."""
    return int(value[0]), int(value[1]), int(value[2])


def _format_exception(err: Exception) -> str:
    """Return a useful exception message for the Home Assistant UI."""
    message = str(err).strip()
    return (
        f"{type(err).__name__}: {message}"
        if message
        else type(err).__name__
    )


async def async_setup(
    hass: HomeAssistant,
    config: ConfigType,
) -> bool:
    """Set up BK-Light actions."""

    async def async_handle_display_text(
        call: ServiceCall,
    ) -> None:
        """Render and display static text."""
        entry, runtime = _get_runtime(
            hass,
            call.data[ATTR_CONFIG_ENTRY_ID],
        )

        try:
            png_bytes = await hass.async_add_executor_job(
                render_text_png,
                call.data[ATTR_TEXT],
                PANEL_WIDTH,
                PANEL_HEIGHT,
                _rgb_color(call.data[ATTR_TEXT_COLOR]),
                _rgb_color(call.data[ATTR_BACKGROUND_COLOR]),
                call.data[ATTR_FONT_SIZE],
                call.data[ATTR_AUTO_FIT],
                call.data[ATTR_HORIZONTAL_ALIGN],
                call.data[ATTR_VERTICAL_ALIGN],
                call.data[ATTR_X_OFFSET],
                call.data[ATTR_Y_OFFSET],
            )

            await runtime.async_stop_animation()
            await runtime.session.send_png(png_bytes, delay=0.2)

        except BkLightError as err:
            _LOGGER.exception(
                "BK-Light text transfer failed for %s",
                entry.title,
            )
            raise HomeAssistantError(
                f"Der Text konnte nicht übertragen werden: "
                f"{_format_exception(err)}"
            ) from err
        except (OSError, RuntimeError, ValueError) as err:
            raise HomeAssistantError(
                f"Der Text konnte nicht gerendert werden: "
                f"{_format_exception(err)}"
            ) from err

    async def async_handle_scroll_text(
        call: ServiceCall,
    ) -> None:
        """Render and start scrolling text."""
        entry, runtime = _get_runtime(
            hass,
            call.data[ATTR_CONFIG_ENTRY_ID],
        )

        try:
            png_frames = await hass.async_add_executor_job(
                render_scroll_frames,
                call.data[ATTR_TEXT],
                PANEL_WIDTH,
                PANEL_HEIGHT,
                _rgb_color(call.data[ATTR_TEXT_COLOR]),
                _rgb_color(call.data[ATTR_BACKGROUND_COLOR]),
                call.data[ATTR_FONT_SIZE],
                call.data[ATTR_AUTO_FIT],
                call.data[ATTR_VERTICAL_ALIGN],
                call.data[ATTR_DIRECTION],
                call.data[ATTR_STEP],
                call.data[ATTR_GAP],
                call.data[ATTR_Y_OFFSET],
            )

            protocol_frames = (
                await runtime.session.async_prepare_frames(png_frames)
            )

            await runtime.async_start_animation(
                hass=hass,
                entry=entry,
                frames=protocol_frames,
                fps=call.data[ATTR_FPS],
                repeat=call.data[ATTR_REPEAT],
            )

        except BkLightError as err:
            _LOGGER.exception(
                "BK-Light scrolling-text transfer failed for %s",
                entry.title,
            )
            raise HomeAssistantError(
                f"Die Laufschrift konnte nicht gestartet werden: "
                f"{_format_exception(err)}"
            ) from err
        except (OSError, RuntimeError, ValueError) as err:
            raise HomeAssistantError(
                f"Die Laufschrift konnte nicht vorbereitet werden: "
                f"{_format_exception(err)}"
            ) from err

    async def async_handle_stop_animation(
        call: ServiceCall,
    ) -> None:
        """Stop the current animation."""
        _entry, runtime = _get_runtime(
            hass,
            call.data[ATTR_CONFIG_ENTRY_ID],
        )
        await runtime.async_stop_animation()

    async def async_handle_display_image(
        call: ServiceCall,
    ) -> None:
        """Load, transform and display an image."""
        entry, runtime = _get_runtime(
            hass,
            call.data[ATTR_CONFIG_ENTRY_ID],
        )

        try:
            if media_selection := call.data.get(ATTR_MEDIA):
                image_path = await async_resolve_local_media_path(
                    hass,
                    media_selection,
                )
                png_bytes = await hass.async_add_executor_job(
                    render_image_path,
                    str(image_path),
                    PANEL_WIDTH,
                    PANEL_HEIGHT,
                    call.data[ATTR_FIT],
                    _rgb_color(call.data[ATTR_BACKGROUND_COLOR]),
                    call.data[ATTR_ROTATION],
                    call.data[ATTR_MIRROR_HORIZONTAL],
                    call.data[ATTR_MIRROR_VERTICAL],
                    call.data[ATTR_BRIGHTNESS],
                    call.data[ATTR_RESAMPLING],
                )
            else:
                png_bytes = await hass.async_add_executor_job(
                    render_image_file,
                    hass.config.path("www", "bk_light"),
                    call.data[ATTR_PATH],
                    PANEL_WIDTH,
                    PANEL_HEIGHT,
                    call.data[ATTR_FIT],
                    _rgb_color(call.data[ATTR_BACKGROUND_COLOR]),
                    call.data[ATTR_ROTATION],
                    call.data[ATTR_MIRROR_HORIZONTAL],
                    call.data[ATTR_MIRROR_VERTICAL],
                    call.data[ATTR_BRIGHTNESS],
                    call.data[ATTR_RESAMPLING],
                )

            await runtime.async_stop_animation()
            await runtime.session.send_png(png_bytes, delay=0.2)

        except ServiceValidationError:
            raise
        except (FileNotFoundError, ImagePathError) as err:
            raise ServiceValidationError(
                f"Ungültige Bilddatei: {_format_exception(err)}"
            ) from err
        except BkLightError as err:
            _LOGGER.exception(
                "BK-Light image transfer failed for %s",
                entry.title,
            )
            raise HomeAssistantError(
                f"Das Bild konnte nicht übertragen werden: "
                f"{_format_exception(err)}"
            ) from err
        except (OSError, RuntimeError, ValueError) as err:
            raise HomeAssistantError(
                f"Das Bild konnte nicht vorbereitet werden: "
                f"{_format_exception(err)}"
            ) from err

    async def async_handle_play_gif(
        call: ServiceCall,
    ) -> None:
        """Load, prepare and play a GIF animation."""
        entry, runtime = _get_runtime(
            hass,
            call.data[ATTR_CONFIG_ENTRY_ID],
        )

        try:
            if media_selection := call.data.get(ATTR_MEDIA):
                gif_path = await async_resolve_local_media_path(
                    hass,
                    media_selection,
                )
                png_frames, durations = (
                    await hass.async_add_executor_job(
                        render_gif_path,
                        str(gif_path),
                        PANEL_WIDTH,
                        PANEL_HEIGHT,
                        call.data[ATTR_FIT],
                        _rgb_color(call.data[ATTR_BACKGROUND_COLOR]),
                        call.data[ATTR_ROTATION],
                        call.data[ATTR_MIRROR_HORIZONTAL],
                        call.data[ATTR_MIRROR_VERTICAL],
                        call.data[ATTR_BRIGHTNESS],
                        call.data[ATTR_RESAMPLING],
                        call.data[ATTR_SPEED],
                        call.data[ATTR_MAX_FPS],
                    )
                )
            else:
                png_frames, durations = (
                    await hass.async_add_executor_job(
                        render_gif_file,
                        hass.config.path("www", "bk_light"),
                        call.data[ATTR_PATH],
                        PANEL_WIDTH,
                        PANEL_HEIGHT,
                        call.data[ATTR_FIT],
                        _rgb_color(call.data[ATTR_BACKGROUND_COLOR]),
                        call.data[ATTR_ROTATION],
                        call.data[ATTR_MIRROR_HORIZONTAL],
                        call.data[ATTR_MIRROR_VERTICAL],
                        call.data[ATTR_BRIGHTNESS],
                        call.data[ATTR_RESAMPLING],
                        call.data[ATTR_SPEED],
                        call.data[ATTR_MAX_FPS],
                    )
                )

            protocol_frames = (
                await runtime.session.async_prepare_frames(png_frames)
            )

            await runtime.async_start_timed_animation(
                hass=hass,
                entry=entry,
                frames=protocol_frames,
                durations=durations,
                repeat=call.data[ATTR_REPEAT],
            )

        except ServiceValidationError:
            raise
        except (FileNotFoundError, AnimationPathError) as err:
            raise ServiceValidationError(
                f"Ungültige GIF-Datei: {_format_exception(err)}"
            ) from err
        except BkLightError as err:
            _LOGGER.exception(
                "BK-Light GIF transfer failed for %s",
                entry.title,
            )
            raise HomeAssistantError(
                f"Das GIF konnte nicht gestartet werden: "
                f"{_format_exception(err)}"
            ) from err
        except (OSError, RuntimeError, ValueError) as err:
            raise HomeAssistantError(
                f"Das GIF konnte nicht vorbereitet werden: "
                f"{_format_exception(err)}"
            ) from err

    action_registrations = (
        (
            SERVICE_DISPLAY_TEXT,
            async_handle_display_text,
            DISPLAY_TEXT_SCHEMA,
        ),
        (
            SERVICE_SCROLL_TEXT,
            async_handle_scroll_text,
            SCROLL_TEXT_SCHEMA,
        ),
        (
            SERVICE_STOP_ANIMATION,
            async_handle_stop_animation,
            STOP_ANIMATION_SCHEMA,
        ),
        (
            SERVICE_DISPLAY_IMAGE,
            async_handle_display_image,
            DISPLAY_IMAGE_SCHEMA,
        ),
        (
            SERVICE_PLAY_GIF,
            async_handle_play_gif,
            PLAY_GIF_SCHEMA,
        ),
    )

    for service_name, handler, schema in action_registrations:
        if not hass.services.has_service(DOMAIN, service_name):
            hass.services.async_register(
                DOMAIN,
                service_name,
                handler,
                schema=schema,
            )

    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up BK-Light from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    name: str = entry.data.get(CONF_NAME, entry.title)

    session = BleDisplaySession(
        hass=hass,
        address=address,
        name=name,
        auto_reconnect=True,
        reconnect_delay=2.0,
        max_retries=2,
        rotation=0,
        brightness=1.0,
        mtu=512,
        log_notifications=False,
        validation_interval=0,
    )

    runtime = BkLightRuntimeData(session=session)
    entry.runtime_data = runtime

    try:
        await hass.config_entries.async_forward_entry_setups(
            entry,
            PLATFORMS,
        )
    except Exception:
        await runtime.async_close()
        raise

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload a BK-Light config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )

    if not unload_ok:
        return False

    runtime: Any = entry.runtime_data

    if isinstance(runtime, BkLightRuntimeData):
        await runtime.async_close()

    return True
