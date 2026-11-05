"""Config flow for Speedport integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
from speedport import Speedport
from speedport.exceptions import LoginException
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host", default="speedport.ip"): str,
        vol.Required("password"): str,
        vol.Optional("https", default=False): bool,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""

    # Same session as async_setup_entry, so the check resolves the host the
    # same way the running integration will (issue #14).
    speedport = Speedport(
        host=data["host"],
        password=data["password"],
        https=data["https"],
        session=aiohttp_client.async_get_clientsession(hass),
    )
    try:
        await speedport.create()
        await speedport.login(data["password"])
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise CannotConnect from exc
    except LoginException as exc:
        raise InvalidAuth from exc

    # Return info that you want to store in the config entry.
    return {"title": "Speedport"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Speedport."""

    VERSION = 1

    async def _async_check(self, data: dict[str, Any]) -> dict[str, str]:
        """Return form errors for the connection data, empty if it works."""
        try:
            await validate_input(self.hass, data)
        except CannotConnect:
            return {"base": "cannot_connect"}
        except InvalidAuth:
            return {"base": "invalid_auth"}
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            return {"base": "unknown"}
        return {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            if not (errors := await self._async_check(user_input)):
                return self.async_create_entry(title="Speedport", data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Change host, https or password of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            # The form drops an empty optional password, so the stored one stays.
            data = {**entry.data, **user_input}
            if not (errors := await self._async_check(data)):
                return self.async_update_reload_and_abort(entry, data=data)

        schema = vol.Schema(
            {
                vol.Required("host", default=entry.data["host"]): str,
                vol.Optional("password"): str,
                vol.Optional("https", default=entry.data["https"]): bool,
            }
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler()


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class OptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "pause_time",
                        default=self.config_entry.options.get("pause_time", 5),
                    ): int
                }
            ),
        )
