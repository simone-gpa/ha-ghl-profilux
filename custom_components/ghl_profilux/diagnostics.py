"""Diagnostica per l'integrazione GHL ProfiLux."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import ProfiLuxConfigEntry

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "serial",
    "serial_number",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ProfiLuxConfigEntry
) -> dict[str, Any]:
    """Restituisce i dati diagnostici della config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "last_update_success": coordinator.last_update_success,
        "system": async_redact_data(
            {
                "firmware": data.firmware,
                "serial": data.serial,
                "product_id": data.product_id,
            },
            TO_REDACT,
        ),
        "alarm": data.alarm,
        "sensors": [
            {
                "index": s.index,
                "type": s.sensor_type,
                "value": s.value,
                "name": s.name,
            }
            for s in data.sensors
        ],
        "switches": [
            {
                "index": sw.index,
                "state": sw.state,
                "function": sw.function,
                "is_manual": sw.is_manual,
                "name": sw.name,
            }
            for sw in data.switches
        ],
    }
