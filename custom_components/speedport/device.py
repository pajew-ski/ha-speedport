import logging
from contextlib import suppress
from datetime import timedelta

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, UPDATE_INTERVAL
from .speedport_api import Speedport
from .speedport_api.exceptions import (
    LoginException,
    LoginPausedError,
    NotAvailableError,
    SessionError,
)

_LOGGER = logging.getLogger(__name__)

# What a router that is rebooting, unreachable or not serving data raises.
UPDATE_ERRORS = (
    aiohttp.ClientError,
    TimeoutError,
    SessionError,
    LoginPausedError,
    NotAvailableError,
)


def async_create_session(hass: HomeAssistant, **kwargs) -> aiohttp.ClientSession:
    """Session with its own cookie jar: the router's session cookies stay out of
    Home Assistant's shared session, and an IP host needs an unsafe jar."""
    return aiohttp_client.async_create_clientsession(
        hass, verify_ssl=False, cookie_jar=aiohttp.CookieJar(unsafe=True), **kwargs
    )


class SpeedportCoordinator(DataUpdateCoordinator[None]):
    def __init__(self, hass: HomeAssistant, device: Speedport):
        """Initialize my coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            name=device.device_name,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self._speedport: Speedport = device

    async def _async_update_data(self) -> None:
        try:
            await self._speedport.update_status()
            # A lost session only pauses the IP data (the API logs it and logs in
            # again after the pause); the status needs no login and stays live.
            with suppress(LoginPausedError, LoginException):
                await self._speedport.update_ip_data()
        except UPDATE_ERRORS as exc:
            raise UpdateFailed(str(exc)) from exc


class SpeedportEntity(CoordinatorEntity[SpeedportCoordinator]):
    _attr_has_entity_name = True

    def __init__(
        self, hass: HomeAssistant, speedport: Speedport, description=None
    ) -> None:
        coordinator = get_coordinator(hass, speedport)
        super().__init__(coordinator)

        self._coordinator = coordinator
        self._speedport: Speedport = speedport
        if description is not None:
            self.entity_description = description
            self._attr_unique_id = f"speedport_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._speedport.serial_number)},
            manufacturer="Telekom",
            name="Speedport",
            model=self._speedport.device_name,
            sw_version=self._speedport.firmware_version,
            configuration_url=self._speedport.api.url,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


def get_coordinator(hass: HomeAssistant, speedport: Speedport) -> SpeedportCoordinator:
    coordinators = hass.data[DOMAIN]["coordinators"]
    if speedport.serial_number in coordinators:
        coordinator: SpeedportCoordinator = hass.data[DOMAIN]["coordinators"][
            speedport.serial_number
        ]
    else:
        coordinator = SpeedportCoordinator(hass, speedport)
        hass.data[DOMAIN]["coordinators"][speedport.serial_number] = coordinator
    return coordinator
