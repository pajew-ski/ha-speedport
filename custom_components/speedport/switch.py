from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from speedport import Speedport

from .const import DOMAIN
from .device import SpeedportEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up entry."""

    speedport: Speedport = hass.data[DOMAIN][entry.entry_id]

    entities: list[SpeedportWlanSwitch] = [SpeedportWifiSwitch(hass, speedport)]

    # Not every model provides all wifi networks, e.g. the Speedport Smart 3
    # does not report "wlan_office_active" because it has no office wifi.
    if speedport.get("wlan_guest_active") is not None:
        entities.append(SpeedportGuestWifiSwitch(hass, speedport))
    else:
        _LOGGER.debug("Skipping guest wifi switch: not supported by this device")

    if speedport.get("wlan_office_active") is not None:
        entities.append(SpeedportOfficeWifiSwitch(hass, speedport))
    else:
        _LOGGER.debug("Skipping office wifi switch: not supported by this device")

    async_add_entities(entities)


class SpeedportWlanSwitch(SwitchEntity, SpeedportEntity):
    _status_key: str = ""

    @property
    def is_on(self) -> bool | None:
        if (status := self._speedport.get(self._status_key)) is None:
            return None
        try:
            return bool(int(status))
        except (TypeError, ValueError):
            return None

    @property
    def available(self) -> bool:
        return super().available and self._speedport.get(self._status_key) is not None


class SpeedportWifiSwitch(SpeedportWlanSwitch):
    _status_key = "use_wlan"

    def __init__(self, hass: HomeAssistant, speedport: Speedport) -> None:
        super().__init__(hass, speedport)
        self._speedport: Speedport = speedport
        self._attr_icon = "mdi:wifi"
        self._attr_name = f"WLAN {speedport.wlan_ssid}"
        self._attr_unique_id = "wifi"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on switch."""
        await self._speedport.wifi_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off switch."""
        await self._speedport.wifi_off()


class SpeedportGuestWifiSwitch(SpeedportWlanSwitch):
    _status_key = "wlan_guest_active"

    def __init__(self, hass: HomeAssistant, speedport: Speedport) -> None:
        super().__init__(hass, speedport)
        self._speedport: Speedport = speedport
        self._attr_icon = "mdi:wifi"
        self._attr_name = f"WLAN {speedport.wlan_guest_ssid}"
        self._attr_unique_id = "wifi_guest"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on switch."""
        await self._speedport.wifi_guest_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off switch."""
        await self._speedport.wifi_guest_off()


class SpeedportOfficeWifiSwitch(SpeedportWlanSwitch):
    _status_key = "wlan_office_active"

    def __init__(self, hass: HomeAssistant, speedport: Speedport) -> None:
        super().__init__(hass, speedport)
        self._speedport: Speedport = speedport
        self._attr_icon = "mdi:wifi"
        self._attr_name = f"WLAN {speedport.wlan_office_ssid}"
        self._attr_unique_id = "wifi_office"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on switch."""
        await self._speedport.wifi_office_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off switch."""
        await self._speedport.wifi_office_off()
