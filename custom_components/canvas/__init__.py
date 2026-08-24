"""Canvas LMS custom component integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CanvasApiClient
from .const import CONF_ACCESS_TOKEN, CONF_BASE_URL
from .coordinator import CanvasDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

type CanvasConfigEntry = ConfigEntry[CanvasDataUpdateCoordinator]

PLATFORMS: list[Platform] = []


async def async_setup_entry(hass: HomeAssistant, entry: CanvasConfigEntry) -> bool:
    """Set up Canvas LMS from a config entry."""
    client = CanvasApiClient(
        base_url=entry.data[CONF_BASE_URL],
        access_token=entry.data[CONF_ACCESS_TOKEN],
        session=async_get_clientsession(hass),
    )
    coordinator = CanvasDataUpdateCoordinator(
        hass=hass,
        client=client,
        entry=entry,
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: CanvasConfigEntry) -> bool:
    """Unload a Canvas LMS config entry."""
    if PLATFORMS:
        return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: CanvasConfigEntry) -> None:
    """Reload a Canvas LMS config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


__all__ = [
    "CanvasApiClient",
    "CanvasConfigEntry",
    "CanvasDataUpdateCoordinator",
    "PLATFORMS",
    "async_reload_entry",
    "async_setup_entry",
    "async_unload_entry",
]
