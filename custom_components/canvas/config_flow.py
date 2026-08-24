"""Config flow for Canvas LMS integration."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CanvasApiClient
from .const import CONF_ACCESS_TOKEN, CONF_BASE_URL, DOMAIN
from .exceptions import (
    CanvasAuthError,
    CanvasConnectionError,
    CanvasError,
    CanvasRateLimitError,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL): str,
        vol.Required(CONF_ACCESS_TOKEN): str,
    }
)

STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
    }
)


def _normalize_url(raw_url: str) -> str:
    """Normalize base URL by trimming whitespace, trailing slashes, and adding scheme."""
    url = raw_url.strip().rstrip("/")
    if not url.lower().startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


class CanvasConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Canvas LMS."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            normalized_url = _normalize_url(user_input[CONF_BASE_URL])
            token = user_input[CONF_ACCESS_TOKEN].strip()

            try:
                session = async_get_clientsession(self.hass)
                client = CanvasApiClient(
                    base_url=normalized_url,
                    access_token=token,
                    session=session,
                )
                user = await client.async_get_current_user()
            except CanvasAuthError:
                errors["base"] = "invalid_auth"
            except (
                CanvasConnectionError,
                CanvasRateLimitError,
                TimeoutError,
                asyncio.TimeoutError,
                aiohttp.ClientError,
            ):
                errors["base"] = "cannot_connect"
            except (CanvasError, Exception):
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(str(user.id))
                self._abort_if_unique_id_configured()

                title = (
                    user.name.strip()
                    if user.name and user.name.strip()
                    else f"User {user.id}"
                )
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_BASE_URL: normalized_url,
                        CONF_ACCESS_TOKEN: token,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication upon token failure."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication with updated credentials."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN].strip()
            base_url = reauth_entry.data[CONF_BASE_URL]

            try:
                session = async_get_clientsession(self.hass)
                client = CanvasApiClient(
                    base_url=base_url,
                    access_token=token,
                    session=session,
                )
                user = await client.async_get_current_user()
            except CanvasAuthError:
                errors["base"] = "invalid_auth"
            except (
                CanvasConnectionError,
                CanvasRateLimitError,
                TimeoutError,
                asyncio.TimeoutError,
                aiohttp.ClientError,
            ):
                errors["base"] = "cannot_connect"
            except (CanvasError, Exception):
                errors["base"] = "unknown"
            else:
                if str(user.id) != reauth_entry.unique_id:
                    return self.async_abort(reason="reauth_account_mismatch")

                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_ACCESS_TOKEN: token},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of Canvas LMS instance URL and token."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            normalized_url = _normalize_url(user_input[CONF_BASE_URL])
            token = user_input[CONF_ACCESS_TOKEN].strip()

            try:
                session = async_get_clientsession(self.hass)
                client = CanvasApiClient(
                    base_url=normalized_url,
                    access_token=token,
                    session=session,
                )
                user = await client.async_get_current_user()
            except CanvasAuthError:
                errors["base"] = "invalid_auth"
            except (
                CanvasConnectionError,
                CanvasRateLimitError,
                TimeoutError,
                asyncio.TimeoutError,
                aiohttp.ClientError,
            ):
                errors["base"] = "cannot_connect"
            except (CanvasError, Exception):
                errors["base"] = "unknown"
            else:
                if str(user.id) != reconfigure_entry.unique_id:
                    return self.async_abort(reason="reauth_account_mismatch")

                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates={
                        CONF_BASE_URL: normalized_url,
                        CONF_ACCESS_TOKEN: token,
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, reconfigure_entry.data
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> CanvasOptionsFlowHandler:
        """Get the options flow handler."""
        return CanvasOptionsFlowHandler()


class CanvasOptionsFlowHandler(OptionsFlow):
    """Handle options for Canvas LMS."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
        )
