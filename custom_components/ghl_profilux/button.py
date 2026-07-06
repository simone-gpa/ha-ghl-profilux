"""Pulsanti per GHL ProfiLux: Feed Pause e Maintenance mode."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ProfiLuxConfigEntry
from .api import ProfiLuxError
from .coordinator import ProfiLuxCoordinator, ProfiLuxEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProfiLuxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea i pulsanti Feed Pause e Maintenance."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            ProfiLuxFeedPauseButton(coordinator, activate=True),
            ProfiLuxFeedPauseButton(coordinator, activate=False),
            ProfiLuxMaintenanceButton(coordinator, activate=True),
            ProfiLuxMaintenanceButton(coordinator, activate=False),
        ]
    )


class ProfiLuxFeedPauseButton(ProfiLuxEntity, ButtonEntity):
    """Attiva o disattiva la pausa alimentazione."""

    def __init__(self, coordinator: ProfiLuxCoordinator, *, activate: bool) -> None:
        """Inizializza il pulsante."""
        super().__init__(coordinator)
        self._activate = activate
        if activate:
            self._attr_name = "Avvia pausa alimentazione"
            self._attr_icon = "mdi:food-off"
            self._attr_unique_id = f"{coordinator.config_entry.entry_id}_feed_pause_on"
        else:
            self._attr_name = "Termina pausa alimentazione"
            self._attr_icon = "mdi:food"
            self._attr_unique_id = f"{coordinator.config_entry.entry_id}_feed_pause_off"

    async def async_press(self) -> None:
        """Invia il comando Feed Pause al ProfiLux."""
        try:
            await self.coordinator.client.async_invoke_feed_pause(activate=self._activate)
        except ProfiLuxError as err:
            raise HomeAssistantError(
                f"Comando Feed Pause fallito: {err}"
            ) from err


class ProfiLuxMaintenanceButton(ProfiLuxEntity, ButtonEntity):
    """Attiva o disattiva la modalità manutenzione."""

    def __init__(self, coordinator: ProfiLuxCoordinator, *, activate: bool) -> None:
        """Inizializza il pulsante."""
        super().__init__(coordinator)
        self._activate = activate
        if activate:
            self._attr_name = "Avvia manutenzione"
            self._attr_icon = "mdi:wrench"
            self._attr_unique_id = f"{coordinator.config_entry.entry_id}_maintenance_on"
        else:
            self._attr_name = "Termina manutenzione"
            self._attr_icon = "mdi:wrench-check"
            self._attr_unique_id = f"{coordinator.config_entry.entry_id}_maintenance_off"

    async def async_press(self) -> None:
        """Invia il comando Maintenance al ProfiLux."""
        try:
            await self.coordinator.client.async_invoke_maintenance(activate=self._activate)
        except ProfiLuxError as err:
            raise HomeAssistantError(
                f"Comando Maintenance fallito: {err}"
            ) from err
