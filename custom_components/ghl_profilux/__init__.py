"""Integrazione Home Assistant per GHL ProfiLux 4/4e (WebSocket locale)."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ProfiLuxAuthError, ProfiLuxClient, ProfiLuxConnectionError
from .const import PLATFORMS
from .coordinator import ProfiLuxCoordinator

# Pre-import delle piattaforme: evita che async_forward_entry_setups chiami
# importlib.import_module() dentro l'event loop (bloccante su Python 3.14+).
from . import binary_sensor, button, sensor, switch  # noqa: F401, E402

_LOGGER = logging.getLogger(__name__)

ProfiLuxConfigEntry = ConfigEntry[ProfiLuxCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ProfiLuxConfigEntry) -> bool:
    """Configura l'integrazione da una config entry."""
    client = ProfiLuxClient(
        hass,
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        async_get_clientsession(hass),
    )
    try:
        await client.async_connect()
    except ProfiLuxAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except ProfiLuxConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = ProfiLuxCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(client.async_disconnect)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ProfiLuxConfigEntry) -> bool:
    """Scarica la config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
