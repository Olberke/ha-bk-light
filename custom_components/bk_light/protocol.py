"""Native BK-Light protocol helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

DEVICE_INFO_OPCODE = 0x8001

# Confirmed or documented iPixel/BK-Light device-type identifiers.
#
# The ACT1026 response tested with this integration contains 0x81.
# The existing ACT1025 alternate response contains 0x83.
KNOWN_DEVICE_DIMENSIONS: dict[int, tuple[int, int]] = {
    0x80: (64, 64),
    0x81: (32, 32),
    0x82: (32, 16),
    0x83: (64, 16),
    0x84: (96, 16),
    0x85: (64, 20),
}

MIN_CLOCK_STYLE = 0
MAX_CLOCK_STYLE = 8


@dataclass(frozen=True, slots=True)
class BkLightDeviceInfo:
    """Information returned by the BK-Light device-info response."""

    device_type: int
    width: int | None
    height: int | None
    raw_response: bytes

    @property
    def dimensions(self) -> tuple[int, int] | None:
        """Return the known panel dimensions."""
        if self.width is None or self.height is None:
            return None

        return self.width, self.height

    @property
    def dimensions_text(self) -> str:
        """Return panel dimensions suitable for logging."""
        if self.width is None or self.height is None:
            return "unknown"

        return f"{self.width}x{self.height}"


def build_time_command(current_time: datetime) -> bytes:
    """Build the BK-Light time synchronization command.

    This command also requests the device-information response used during
    the initial protocol handshake.
    """
    hour = current_time.hour
    minute = current_time.minute
    second = current_time.second

    if not 0 <= hour <= 23:
        raise ValueError("Hour must be between 0 and 23")

    if not 0 <= minute <= 59:
        raise ValueError("Minute must be between 0 and 59")

    if not 0 <= second <= 59:
        raise ValueError("Second must be between 0 and 59")

    return bytes(
        (
            8,       # Command length
            0,       # Reserved
            1,       # Command ID
            0x80,    # Command type
            hour,
            minute,
            second,
            0,       # Language/reserved
        )
    )


def build_clock_mode_command(
    current_time: datetime,
    *,
    style: int = 1,
    format_24h: bool = True,
    show_date: bool = True,
) -> bytes:
    """Build the native BK-Light clock-mode command."""
    if not MIN_CLOCK_STYLE <= style <= MAX_CLOCK_STYLE:
        raise ValueError(
            f"Clock style must be between "
            f"{MIN_CLOCK_STYLE} and {MAX_CLOCK_STYLE}"
        )

    year = current_time.year % 100
    month = current_time.month
    day = current_time.day
    day_of_week = current_time.isoweekday()

    if not 0 <= year <= 99:
        raise ValueError("Year must be between 0 and 99")

    if not 1 <= month <= 12:
        raise ValueError("Month must be between 1 and 12")

    if not 1 <= day <= 31:
        raise ValueError("Day must be between 1 and 31")

    if not 1 <= day_of_week <= 7:
        raise ValueError("Day of week must be between 1 and 7")

    return bytes(
        (
            11,                      # Command length
            0,                       # Reserved
            6,                       # Command ID
            1,                       # Command type
            style,
            1 if format_24h else 0,
            1 if show_date else 0,
            year,
            month,
            day,
            day_of_week,
        )
    )


def parse_device_info_response(
    response: bytes,
) -> BkLightDeviceInfo:
    """Parse a BK-Light device-info notification.

    The notification starts with:

    - two-byte little-endian message length;
    - two-byte little-endian opcode;
    - one-byte device-type identifier.

    Remaining bytes are intentionally preserved but not interpreted until
    their exact meaning has been verified against real hardware.
    """
    if len(response) < 5:
        raise ValueError(
            "Device-info response must contain at least 5 bytes"
        )

    declared_length = int.from_bytes(
        response[0:2],
        byteorder="little",
        signed=False,
    )

    if declared_length != len(response):
        raise ValueError(
            "Device-info response length mismatch: "
            f"declared {declared_length}, received {len(response)}"
        )

    opcode = int.from_bytes(
        response[2:4],
        byteorder="little",
        signed=False,
    )

    if opcode != DEVICE_INFO_OPCODE:
        raise ValueError(
            "Unexpected device-info opcode: "
            f"0x{opcode:04X}"
        )

    device_type = response[4]
    dimensions = KNOWN_DEVICE_DIMENSIONS.get(device_type)

    if dimensions is None:
        width = None
        height = None
    else:
        width, height = dimensions

    return BkLightDeviceInfo(
        device_type=device_type,
        width=width,
        height=height,
        raw_response=response,
    )