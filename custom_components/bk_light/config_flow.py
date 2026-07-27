"""Config flow for the BK-Light LED Matrix integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from .const import DEVICE_NAME_PREFIX, DOMAIN


class BkLightConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BK-Light."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the BK-Light config flow."""
        self._discovery_info: bluetooth.BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[
            str,
            bluetooth.BluetoothServiceInfoBleak,
        ] = {}

    async def async_step_bluetooth(
        self,
        discovery_info: bluetooth.BluetoothServiceInfoBleak,
    ) -> ConfigFlowResult:
        """Handle automatic Bluetooth discovery."""
        name = self._device_name(discovery_info)

        if not name.upper().startswith(DEVICE_NAME_PREFIX):
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": name}

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Confirm a Bluetooth-discovered BK-Light device."""
        if self._discovery_info is None:
            return self.async_abort(reason="no_devices_found")

        name = self._device_name(self._discovery_info)

        if user_input is not None:
            return self._create_entry(self._discovery_info)

        self._set_confirm_only()

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": name},
        )

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle manually initiated setup."""
        if user_input is not None:
            address: str = user_input[CONF_ADDRESS]
            discovery_info = self._discovered_devices[address]

            await self.async_set_unique_id(
                address,
                raise_on_progress=False,
            )
            self._abort_if_unique_id_configured()

            return self._create_entry(discovery_info)

        await bluetooth.async_request_active_scan(self.hass)

        configured_addresses = self._async_current_ids(
            include_ignore=False,
        )

        for discovery_info in bluetooth.async_discovered_service_info(
            self.hass,
            connectable=True,
        ):
            address = discovery_info.address
            name = self._device_name(discovery_info)

            if not name.upper().startswith(DEVICE_NAME_PREFIX):
                continue
            if address in configured_addresses:
                continue

            self._discovered_devices[address] = discovery_info

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        device_labels = {
            address: (
                f"{self._device_name(discovery_info)} "
                f"({discovery_info.address})"
            )
            for address, discovery_info in self._discovered_devices.items()
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(device_labels),
                }
            ),
        )

    def _create_entry(
        self,
        discovery_info: bluetooth.BluetoothServiceInfoBleak,
    ) -> ConfigFlowResult:
        """Create the BK-Light config entry."""
        name = self._device_name(discovery_info)

        return self.async_create_entry(
            title=name,
            data={
                CONF_ADDRESS: discovery_info.address,
                CONF_NAME: name,
            },
        )

    @staticmethod
    def _device_name(
        discovery_info: bluetooth.BluetoothServiceInfoBleak,
    ) -> str:
        """Return a human-readable device name."""
        return (
            discovery_info.name
            or discovery_info.device.name
            or f"BK-Light {discovery_info.address}"
        )
