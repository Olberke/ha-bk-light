"""Native BK-Light protocol helpers."""

from __future__ import annotations

from dataclasses import dataclass

DEVICE_INFO_OPCODE = 0x8001

# Confirmed or documented iPixel/BK-Light device-type identifiers.
#
# The ACT1026 response currently used by this integration contains 0x81.
# The existing ACT1025 alternate response contains 0x83.
KNOWN_DEVICE_DIMENSIONS: dict[int, tuple[int, int]] = {
    0x80: (64, 64),
    0x81: (32, 32),
    0x82: (32, 16),
    0x83: (64, 16),
    0x84: (96, 16),
    0x85: (64, 20),
}


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


def parse_device_info_response(response: bytes) -> BkLightDeviceInfo:
    """Parse a BK-Light device-info notification.

    The notification starts with:

    - two-byte little-endian message length;
    - two-byte little-endian opcode;
    - one-byte device-type identifier.

    Remaining bytes are intentionally preserved but not interpreted until their
    exact meaning has been verified against real hardware.
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