"""Switch per GHL ProfiLux: prese in modalità manuale (AlwaysOn/AlwaysOff).

Solo le prese già impostate su AlwaysOn o AlwaysOff nel ProfiLux vengono
esposte come switch HA — le prese governate da timer, automazioni ProfiLux
o altri sistemi non sono controllabili da qui per sicurezza.

# NOTE: da verificare su hardware reale — il comando scrive in EEPROM il
# DeviceMode della presa (29=AlwaysOn, 30=AlwaysOff). Testare con cautela.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ProfiLuxConfigEntry
from .api import ProfiLuxError
from .coordinator import ProfiLuxCoordinator, ProfiLuxEntity, SwitchData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProfiLuxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea switch solo per le prese in modalità manuale."""
    coordinator = entry.runtime_data
    async_add_entities(
        ProfiLuxSwitch(coordinator, sw)
        for sw in coordinator.data.switches
        if sw.is_manual
    )


class ProfiLuxSwitch(ProfiLuxEntity, SwitchEntity):
    """Switch per una presa ProfiLux in modalità manuale."""

    _attr_icon = "mdi:power-socket-eu"

    def __init__(self, coordinator: ProfiLuxCoordinator, sw: SwitchData) -> None:
        """Inizializza lo switch."""
        super().__init__(coordinator)
        self._index = sw.index
        self._attr_name = sw.name or f"Presa {sw.index + 1}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_switch_{sw.index}"

    def _get_sw(self) -> SwitchData | None:
        for sw in self.coordinator.data.switches:
            if sw.index == self._index:
                return sw
        return None

    @property
    def is_on(self) -> bool | None:
        """Stato corrente della presa."""
        sw = self._get_sw()
        return sw.is_on if sw else None

    @property
    def available(self) -> bool:
        """Disponibile solo se ancora in modalità manuale."""
        sw = self._get_sw()
        return super().available and sw is not None and sw.is_manual

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Accende la presa (AlwaysOn)."""
        try:
            await self.coordinator.client.async_set_switch(self._index, on=True)
        except ProfiLuxError as err:
            raise HomeAssistantError(f"Accensione presa {self._index + 1} fallita: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Spegne la presa (AlwaysOff)."""
        try:
            await self.coordinator.client.async_set_switch(self._index, on=False)
        except ProfiLuxError as err:
            raise HomeAssistantError(f"Spegnimento presa {self._index + 1} fallito: {err}") from err
        await self.coordinator.async_request_refresh()
