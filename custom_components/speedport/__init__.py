"""The Speedport integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceEntry,
    format_mac,
)

from .config_flow import OptionsFlowHandler
from .const import DOMAIN
from .device import UPDATE_ERRORS, async_create_session
from .speedport_api import Speedport
from .speedport_api.exceptions import LoginException

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Speedport from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    speedport = Speedport(
        host=entry.data["host"],
        password=entry.data["password"],
        https=entry.data["https"],
        session=async_create_session(hass),
        pause_time=entry.options.get("pause_time", 5),
    )
    try:
        await speedport.create()
    except UPDATE_ERRORS as exc:
        raise ConfigEntryNotReady(str(exc)) from exc
    # The IP data needs a login and may arrive later (sensor.py adds its sensors
    # then). Failing the setup over it would make Home Assistant retry, and each
    # retry would log in again and push whoever uses the web UI out (#19).
    try:
        await speedport.update_ip_data()
    except LoginException as exc:
        raise ConfigEntryError(f"The router rejected the login: {exc}") from exc
    except UPDATE_ERRORS:
        pass
    hass.data[DOMAIN][entry.entry_id] = speedport
    hass.data[DOMAIN]["coordinators"] = {}

    entry.async_on_unload(entry.add_update_listener(update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def update_listener(hass, entry):
    """Handle options update."""
    speedport: Speedport = hass.data[DOMAIN][entry.entry_id]
    speedport.set_pause_time(entry.options.get("pause_time", 5))


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> bool:
    """Allow removing a client device the router no longer reports."""
    if any(domain == DOMAIN for domain, _ in device.identifiers):
        return False  # the router itself
    speedport: Speedport = hass.data[DOMAIN][entry.entry_id]
    reported = {format_mac(mac) for mac in await speedport.devices}
    return not any(
        kind == CONNECTION_NETWORK_MAC and mac in reported
        for kind, mac in device.connections
    )
