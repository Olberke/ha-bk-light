"""Bluetooth transport for BK-Light LED matrices in Home Assistant."""

from __future__ import annotations

import asyncio
import binascii
from collections.abc import Callable, Sequence
from io import BytesIO
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BLEAK_RETRY_EXCEPTIONS,
    BleakClientWithServiceCache,
    establish_connection,
)
from PIL import Image, ImageEnhance

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothReachabilityIntent
from homeassistant.core import HomeAssistant

from .protocol import (
    BkLightDeviceInfo,
    build_clock_mode_command,
    build_time_command,
    parse_device_info_response,
)


_LOGGER = logging.getLogger(__name__)

UUID_WRITE = "0000fa02-0000-1000-8000-00805f9b34fb"
UUID_NOTIFY = "0000fa03-0000-1000-8000-00805f9b34fb"

HANDSHAKE_SECOND = bytes.fromhex("04 00 05 80")

ACK_STAGE_ONE = bytes.fromhex("0C 00 01 80 81 06 32 00 00 01 00 01")
ACK_STAGE_ONE_ALT = bytes.fromhex(
    "0B 00 01 80 83 06 32 00 00 01 00"
)  # ACT1025 64x16
ACK_STAGE_TWO = bytes.fromhex("08 00 05 80 0B 03 07 02")
ACK_STAGE_TWO_ALT = bytes.fromhex(
    "08 00 05 80 0E 03 07 01"
)  # ACT1025 64x16
ACK_STAGE_THREE = bytes.fromhex("05 00 02 00 03")

FRAME_VALIDATION = bytes.fromhex("05 00 00 01 00")

DEFAULT_ACK_TIMEOUT = 5.0
DEFAULT_VALIDATION_INTERVAL = 30

_RETRYABLE_EXCEPTIONS = (
    *BLEAK_RETRY_EXCEPTIONS,
    ConnectionError,
    OSError,
    RuntimeError,
)


class BkLightError(Exception):
    """Base exception for BK-Light communication errors."""


class BkLightUnavailableError(BkLightError):
    """Raised when no connectable Bluetooth path is available."""


class BkLightProtocolError(BkLightError):
    """Raised when the panel does not acknowledge a protocol operation."""


def bytes_to_hex(data: bytes) -> str:
    """Return bytes in the format used by the original toolkit logs."""
    return "-".join(f"{value:02X}" for value in data)


def build_frame(png_bytes: bytes) -> bytes:
    """Wrap PNG data in a BK-Light image frame."""
    data_length = len(png_bytes)
    total_length = data_length + 15

    if data_length > 0xFFFF:
        raise ValueError(
            f"PNG payload is too large for the BK-Light frame: {data_length} bytes"
        )
    if total_length > 0xFFFF:
        raise ValueError(
            f"BK-Light frame is too large: {total_length} bytes"
        )

    frame = bytearray()
    frame += total_length.to_bytes(2, "little")
    frame.append(0x02)
    frame += b"\x00\x00"
    frame += data_length.to_bytes(2, "little")
    frame += b"\x00\x00"
    frame += binascii.crc32(png_bytes).to_bytes(4, "little")
    frame += b"\x00\x65"
    frame += png_bytes
    return bytes(frame)


def adjust_image(
    png_bytes: bytes,
    rotation: int,
    brightness: float,
) -> bytes:
    """Rotate and adjust a PNG image.

    This function performs CPU-bound Pillow work and must be called through
    Home Assistant's executor from asynchronous code.
    """
    if brightness < 0:
        raise ValueError("Brightness must be greater than or equal to 0")

    with Image.open(BytesIO(png_bytes)) as source:
        image = source.convert("RGB")

    if rotation:
        image = image.rotate(rotation % 360, expand=False)

    if brightness != 1.0:
        image = ImageEnhance.Brightness(image).enhance(brightness)

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def prepare_frame(
    png_bytes: bytes,
    rotation: int,
    brightness: float,
) -> bytes:
    """Prepare a complete BK-Light frame from PNG bytes.

    When no transformation is required, the original PNG is wrapped directly.
    This avoids decoding and re-encoding every animation frame with Pillow.
    """
    if not png_bytes:
        raise ValueError("png_bytes must not be empty")

    if rotation % 360 == 0 and brightness == 1.0:
        return build_frame(png_bytes)

    return build_frame(
        adjust_image(
            png_bytes,
            rotation,
            brightness,
        )
    )


def prepare_frames(
    png_frames: Sequence[bytes],
    rotation: int,
    brightness: float,
) -> tuple[bytes, ...]:
    """Prepare multiple complete BK-Light frames for RAM playback."""
    if not png_frames:
        raise ValueError("png_frames must not be empty")

    return tuple(
        prepare_frame(
            png_bytes,
            rotation,
            brightness,
        )
        for png_bytes in png_frames
    )


class AckWatcher:
    """Track acknowledgements received through the notify characteristic."""

    def __init__(
        self,
        address: str,
        log_notifications: bool,
    ) -> None:
        self.address = address
        self.log_notifications = log_notifications
        self.stage_one = asyncio.Event()
        self.stage_two = asyncio.Event()
        self.stage_three = asyncio.Event()
        self.stage_one_payload: bytes | None = None

    def reset(self) -> None:
        """Clear all acknowledgement events."""
        self.stage_one.clear()
        self.stage_two.clear()
        self.stage_three.clear()

    def handler(
        self,
        _sender: BleakGATTCharacteristic,
        data: bytearray,
    ) -> None:
        """Handle a GATT notification."""
        payload = bytes(data)

        if self.log_notifications:
            _LOGGER.debug(
                "%s: notification %s",
                self.address,
                bytes_to_hex(payload),
            )

        if payload in (ACK_STAGE_ONE, ACK_STAGE_ONE_ALT):
            self.stage_one_payload = payload
            self.stage_one.set()

        elif payload in (ACK_STAGE_TWO, ACK_STAGE_TWO_ALT):
            self.stage_two.set()
        elif payload == ACK_STAGE_THREE:
            self.stage_three.set()
        elif self.log_notifications:
            _LOGGER.debug(
                "%s: unhandled notification %s",
                self.address,
                bytes_to_hex(payload),
            )


async def wait_for_ack(
    event: asyncio.Event,
    label: str,
    address: str,
    timeout: float,
    log_notifications: bool,
) -> None:
    """Wait until the requested protocol acknowledgement arrives."""
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except TimeoutError as err:
        if log_notifications:
            _LOGGER.debug("%s: %s timed out", address, label)
        raise BkLightProtocolError(
            f"{address}: no acknowledgement for {label} within {timeout:.1f}s"
        ) from err

    if log_notifications:
        _LOGGER.debug("%s: %s acknowledged", address, label)


class BleDisplaySession:
    """Manage one BK-Light BLE connection.

    The session uses Home Assistant's shared Bluetooth manager and therefore
    supports local adapters as well as connectable remote adapters.
    """
    def _local_now(self) -> datetime:
        """Return the current time in the configured Home Assistant timezone."""
        return datetime.now(
            ZoneInfo(self.hass.config.time_zone)
        )

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        *,
        name: str | None = None,
        auto_reconnect: bool = True,
        reconnect_delay: float = 2.0,
        rotation: int = 0,
        brightness: float = 1.0,
        mtu: int | None = 512,
        log_notifications: bool = False,
        max_retries: int = 3,
        scan_timeout: float = 6.0,
        ack_timeout: float = DEFAULT_ACK_TIMEOUT,
        validation_interval: int = DEFAULT_VALIDATION_INTERVAL,
    ) -> None:
        if not address:
            raise ValueError("A Bluetooth address is required")
        if reconnect_delay < 0:
            raise ValueError("reconnect_delay must be greater than or equal to 0")
        if brightness < 0:
            raise ValueError("brightness must be greater than or equal to 0")
        if max_retries < 0:
            raise ValueError("max_retries must be greater than or equal to 0")
        if scan_timeout <= 0:
            raise ValueError("scan_timeout must be greater than 0")
        if ack_timeout <= 0:
            raise ValueError("ack_timeout must be greater than 0")
        if validation_interval < 0:
            raise ValueError(
                "validation_interval must be greater than or equal to 0"
            )

        self.hass = hass
        self.address = address.upper()
        self.name = name or f"BK-Light {self.address}"
        self.auto_reconnect = auto_reconnect
        self.reconnect_delay = reconnect_delay
        self.rotation = rotation
        self.brightness = brightness
        self.mtu = mtu
        self.log_notifications = log_notifications
        self.max_retries = max_retries
        self.scan_timeout = scan_timeout
        self.ack_timeout = ack_timeout
        self.validation_interval = validation_interval

        self.client: BleakClientWithServiceCache | None = None
        self.watcher = AckWatcher(self.address, log_notifications)
        self._device_info: BkLightDeviceInfo | None = None

        self._handshake_primed = False
        self._frames_since_validation = 0
        self._connect_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._closing = False

    @property
    def is_connected(self) -> bool:
        """Return whether the BLE client currently reports a connection."""
        return bool(self.client and self.client.is_connected)

    @property
    def device_info(self) -> BkLightDeviceInfo | None:
        """Return the most recently received device information."""
        return self._device_info

    def set_rotation(self, rotation: int) -> None:
        """Update image rotation for future frames."""
        self.rotation = rotation

    def set_brightness(self, brightness: float) -> None:
        """Update software brightness for future frames."""
        if brightness < 0:
            raise ValueError("brightness must be greater than or equal to 0")
        self.brightness = brightness

    def _handle_disconnect(
        self,
        client: BleakClientWithServiceCache,
    ) -> None:
        """Handle an unexpected or requested BLE disconnect."""
        if self.client is client:
            self.client = None

        self._reset_protocol_state()
        _LOGGER.debug("%s: Bluetooth connection closed", self.address)

    def _reset_protocol_state(self) -> None:
        """Force the next frame to perform a complete handshake."""
        self._handshake_primed = False
        self._frames_since_validation = 0
        self.watcher.reset()

    def _latest_ble_device_callback(
        self,
        fallback: BLEDevice,
    ) -> Callable[[], BLEDevice]:
        """Return a callback that follows the best available HA adapter."""

        def _latest_ble_device() -> BLEDevice:
            return (
                bluetooth.async_ble_device_from_address(
                    self.hass,
                    self.address,
                    connectable=True,
                )
                or fallback
            )

        return _latest_ble_device

    async def _async_resolve_device(self) -> BLEDevice:
        """Resolve the nearest connectable BLEDevice through Home Assistant."""
        device = bluetooth.async_ble_device_from_address(
            self.hass,
            self.address,
            connectable=True,
        )
        if device is not None:
            return device

        # Ask AUTO-mode scanners for a one-shot active scan. This is especially
        # useful when the panel has not advertised recently.
        request_active_scan = getattr(
            bluetooth,
            "async_request_active_scan",
            None,
        )
        if request_active_scan is not None:
            await request_active_scan(
                self.hass,
                duration=self.scan_timeout,
            )

        device = bluetooth.async_ble_device_from_address(
            self.hass,
            self.address,
            connectable=True,
        )
        if device is not None:
            return device

        reason = bluetooth.async_address_reachability_diagnostics(
            self.hass,
            self.address,
            BluetoothReachabilityIntent.CONNECTION,
        )
        raise BkLightUnavailableError(
            f"{self.address} is not reachable through a connectable "
            f"Home Assistant Bluetooth adapter: {reason}"
        )

    async def _async_disconnect_locked(self) -> None:
        """Disconnect while the connection lock is held."""
        client = self.client
        self.client = None
        self._reset_protocol_state()

        if client is None:
            return

        try:
            if client.is_connected:
                try:
                    await client.stop_notify(UUID_NOTIFY)
                except Exception as err:  # Cleanup must not mask the original error.
                    _LOGGER.debug(
                        "%s: could not stop notifications during cleanup: %s",
                        self.address,
                        err,
                    )

                await asyncio.sleep(0.1)

            await client.disconnect()
        except Exception as err:  # Cleanup must not mask the original error.
            _LOGGER.debug(
                "%s: disconnect cleanup failed: %s",
                self.address,
                err,
            )

    async def async_disconnect(self) -> None:
        """Disconnect the panel and release its Bluetooth connection slot."""
        async with self._connect_lock:
            await self._async_disconnect_locked()

    async def _async_exchange_mtu_if_supported(
        self,
        client: BleakClientWithServiceCache,
    ) -> None:
        """Request the configured MTU when the active backend exposes it."""
        if not self.mtu:
            return

        exchange_mtu = getattr(client, "exchange_mtu", None)
        if exchange_mtu is None:
            _LOGGER.debug(
                "%s: active Bluetooth backend does not expose MTU exchange",
                self.address,
            )
            return

        try:
            await exchange_mtu(self.mtu)
        except _RETRYABLE_EXCEPTIONS as err:
            # MTU exchange is an optimization. The write itself determines
            # whether the backend supports this panel's long ATT operation.
            _LOGGER.debug(
                "%s: MTU exchange was not available: %s",
                self.address,
                err,
            )

    async def _connect(self) -> None:
        """Establish a BLE connection using Home Assistant's adapter routing."""
        async with self._connect_lock:
            if self.is_connected:
                return

            await self._async_disconnect_locked()
            device = await self._async_resolve_device()

            _LOGGER.debug(
                "%s: connecting through Home Assistant Bluetooth",
                self.address,
            )

            client: BleakClientWithServiceCache | None = None
            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    device,
                    self.name,
                    disconnected_callback=self._handle_disconnect,
                    max_attempts=self.max_retries + 1,
                    ble_device_callback=self._latest_ble_device_callback(device),
                )
                self.client = client

                await self._async_exchange_mtu_if_supported(client)
                await client.start_notify(UUID_NOTIFY, self.watcher.handler)

                self._reset_protocol_state()
                _LOGGER.debug("%s: connected and notifications enabled", self.address)
            except Exception:
                if client is not None:
                    self.client = client
                await self._async_disconnect_locked()
                raise

    async def _ensure_connected(self) -> None:
        """Connect when no usable connection currently exists."""
        if not self.is_connected:
            await self._connect()

    async def __aenter__(self) -> BleDisplaySession:
        """Connect when entering an async context."""
        self._closing = False
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """Disconnect when leaving an async context."""
        await self.async_close()

    async def async_close(self) -> None:
        """Stop new transfers and close the BLE session."""
        self._closing = True
        async with self._send_lock:
            await self.async_disconnect()

    async def async_prepare_frame(
        self,
        png_bytes: bytes,
    ) -> bytes:
        """Prepare one BK-Light protocol frame outside the event loop."""
        if not png_bytes:
            raise ValueError("png_bytes must not be empty")

        return await self.hass.async_add_executor_job(
            prepare_frame,
            png_bytes,
            self.rotation,
            self.brightness,
        )

    async def async_prepare_frames(
        self,
        png_frames: Sequence[bytes],
    ) -> tuple[bytes, ...]:
        """Prepare animation frames once for direct playback from RAM."""
        if not png_frames:
            raise ValueError("png_frames must not be empty")

        return await self.hass.async_add_executor_job(
            prepare_frames,
            tuple(png_frames),
            self.rotation,
            self.brightness,
        )
    async def async_display_clock(
        self,
        *,
        style: int = 1,
        format_24h: bool = True,
        show_date: bool = True,
        delay: float = 0.2,
    ) -> None:
        """Synchronize time and activate the native panel clock."""
        if delay < 0:
            raise ValueError(
                "delay must be greater than or equal to 0"
            )

        if self._closing:
            raise BkLightError(
                "The BK-Light session is closing"
            )

        current_time = self._local_now()

        time_command = build_time_command(current_time)
        clock_command = build_clock_mode_command(
            current_time,
            style=style,
            format_24h=format_24h,
            show_date=show_date,
        )

        attempts = (
            self.max_retries + 1
            if self.auto_reconnect
            else 1
        )

        async with self._send_lock:
            for attempt in range(1, attempts + 1):
                try:
                    await self._async_display_clock_once(
                        time_command=time_command,
                        clock_command=clock_command,
                        style=style,
                        format_24h=format_24h,
                        show_date=show_date,
                        delay=delay,
                    )
                    return
                except (
                    *_RETRYABLE_EXCEPTIONS,
                    BkLightError,
                ) as err:
                    self._reset_protocol_state()
                    await self.async_disconnect()

                    if attempt >= attempts:
                        raise

                    _LOGGER.debug(
                        "%s: clock command failed on attempt "
                        "%d/%d: %s",
                        self.address,
                        attempt,
                        attempts,
                        err,
                    )

                    await asyncio.sleep(
                        self.reconnect_delay
                    )

        raise AssertionError("Unreachable")

    async def _async_display_clock_once(
        self,
        *,
        time_command: bytes,
        clock_command: bytes,
        style: int,
        format_24h: bool,
        show_date: bool,
        delay: float,
    ) -> None:
        """Send the native clock command once."""
        await self._ensure_connected()

        client = self.client

        if client is None or not client.is_connected:
            raise ConnectionError(
                f"{self.address}: Bluetooth connection was lost"
            )

        self.watcher.reset()
        self.watcher.stage_one_payload = None

        # The time synchronization command also returns device
        # information through the notification characteristic.
        await client.write_gatt_char(
            UUID_WRITE,
            time_command,
            response=False,
        )

        await wait_for_ack(
            self.watcher.stage_one,
            "clock time synchronization",
            self.address,
            self.ack_timeout,
            self.log_notifications,
        )

        stage_one_payload = self.watcher.stage_one_payload

        if stage_one_payload is None:
            raise BkLightProtocolError(
                f"{self.address}: clock time synchronization "
                "contained no device-information payload"
            )

        try:
            device_info = parse_device_info_response(
                stage_one_payload
            )
        except ValueError as err:
            raise BkLightProtocolError(
                f"{self.address}: invalid device-info "
                f"response during clock synchronization: {err}"
            ) from err

        if device_info != self._device_info:
            _LOGGER.info(
                "%s: detected BK-Light device type 0x%02X, "
                "dimensions %s, raw response %s",
                self.address,
                device_info.device_type,
                device_info.dimensions_text,
                bytes_to_hex(device_info.raw_response),
            )

        self._device_info = device_info

        await asyncio.sleep(delay)

        # Native clock commands are short control commands and are
        # written without a GATT response, matching the documented
        # protocol implementations.
        await client.write_gatt_char(
            UUID_WRITE,
            clock_command,
            response=False,
        )

        await asyncio.sleep(delay)

        # Force a complete image handshake if a later action replaces
        # the clock with a text, image or animation frame.
        self._reset_protocol_state()

        _LOGGER.info(
            "%s: native clock activated: style=%d, "
            "24h=%s, date=%s",
            self.address,
            style,
            format_24h,
            show_date,
        )

    async def send_png(
        self,
        png_bytes: bytes,
        delay: float = 0.2,
    ) -> None:
        """Prepare and send one PNG image."""
        frame = await self.async_prepare_frame(png_bytes)
        await self.send_frame(frame, delay)

    async def send_frame(
        self,
        frame: bytes,
        delay: float = 0.2,
    ) -> None:
        """Send one complete BK-Light frame.

        Only one transfer may run at a time. This prevents two Home Assistant
        actions from interleaving their handshakes and image payloads.
        """
        if not frame:
            raise ValueError("frame must not be empty")
        if delay < 0:
            raise ValueError("delay must be greater than or equal to 0")
        if self._closing:
            raise BkLightError("The BK-Light session is closing")

        attempts = self.max_retries + 1 if self.auto_reconnect else 1

        async with self._send_lock:
            for attempt in range(1, attempts + 1):
                try:
                    await self._async_send_frame_once(frame, delay)
                    return
                except (*_RETRYABLE_EXCEPTIONS, BkLightError) as err:
                    self._reset_protocol_state()
                    await self.async_disconnect()

                    if attempt >= attempts:
                        raise

                    _LOGGER.debug(
                        "%s: frame transfer failed on attempt %d/%d: %s",
                        self.address,
                        attempt,
                        attempts,
                        err,
                    )
                    await asyncio.sleep(self.reconnect_delay)

        raise AssertionError("Unreachable")

    async def _async_send_frame_once(
        self,
        frame: bytes,
        delay: float,
    ) -> None:
        """Send a frame once; retry handling is owned by send_frame."""
        await self._ensure_connected()

        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError(f"{self.address}: Bluetooth connection was lost")

        self.watcher.reset()

        if not self._handshake_primed:
            self.watcher.stage_one_payload = None

            time_command = build_time_command(self._local_now())

            await client.write_gatt_char(
                UUID_WRITE,
                time_command,
                response=False,
            )

            await wait_for_ack(
                self.watcher.stage_one,
                "handshake stage one",
                self.address,
                self.ack_timeout,
                self.log_notifications,
            )
            stage_one_payload = self.watcher.stage_one_payload

            if stage_one_payload is None:
                raise BkLightProtocolError(
                    f"{self.address}: stage-one acknowledgement contained no payload"
                )

            try:
                device_info = parse_device_info_response(stage_one_payload)
            except ValueError as err:
                raise BkLightProtocolError(
                    f"{self.address}: invalid device-info response: {err}"
                ) from err

            if device_info != self._device_info:
                _LOGGER.info(
                    "%s: detected BK-Light device type 0x%02X, "
                    "dimensions %s, raw response %s",
                    self.address,
                    device_info.device_type,
                    device_info.dimensions_text,
                    bytes_to_hex(device_info.raw_response),
                )

            self._device_info = device_info
            await asyncio.sleep(delay)

            self.watcher.stage_two.clear()
            try:
                await client.write_gatt_char(
                    UUID_WRITE,
                    HANDSHAKE_SECOND,
                    response=False,
                )
                await wait_for_ack(
                    self.watcher.stage_two,
                    "handshake stage two",
                    self.address,
                    self.ack_timeout,
                    self.log_notifications,
                )
            except BkLightProtocolError:
                # ACT1025 firmware variants may not acknowledge stage two.
                _LOGGER.debug(
                    "%s: stage-two acknowledgement omitted by panel",
                    self.address,
                )

            await asyncio.sleep(delay)
            self._handshake_primed = True

        # The BK-Light protocol expects the complete framed PNG as one logical
        # acknowledged write. Whether that long ATT write works depends on the
        # selected local adapter or connectable Bluetooth proxy.
        await client.write_gatt_char(
            UUID_WRITE,
            frame,
            response=True,
        )
        await wait_for_ack(
            self.watcher.stage_three,
            "frame",
            self.address,
            self.ack_timeout,
            self.log_notifications,
        )

        self._frames_since_validation += 1
        if (
            self.validation_interval
            and self._frames_since_validation >= self.validation_interval
        ):
            await client.write_gatt_char(
                UUID_WRITE,
                FRAME_VALIDATION,
                response=False,
            )
            self._frames_since_validation = 0

        await asyncio.sleep(delay)
