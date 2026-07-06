"""Binary sensor per GHL ProfiLux: allarme attivo e stato prese."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ProfiLuxConfigEntry
from .coordinator import ProfiLuxCoordinator, ProfiLuxEntity, SwitchData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProfiLuxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea il sensore di allarme e le prese non manuali come binary sensor."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [ProfiLuxAlarmSensor(coordinator)]

    # Prese non in modalità manuale: solo lettura (binary sensor)
    for sw in coordinator.data.switches:
        if not sw.is_manual:
            entities.append(ProfiLuxSwitchStateSensor(coordinator, sw))

    async_add_entities(entities)


class ProfiLuxAlarmSensor(ProfiLuxEntity, BinarySensorEntity):
    """Sensore binario: allarme attivo sul ProfiLux."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Allarme"
    _attr_icon = "mdi:alarm-light"

    def __init__(self, coordinator: ProfiLuxCoordinator) -> None:
        """Inizializza il sensore di allarme."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_alarm"

    @property
    def is_on(self) -> bool | None:
        """True se c'è un allarme attivo."""
        return self.coordinator.data.alarm


class ProfiLuxSwitchStateSensor(ProfiLuxEntity, BinarySensorEntity):
    """Sensore binario per lo stato di una presa non manuale (sola lettura)."""

    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, coordinator: ProfiLuxCoordinator, sw: SwitchData) -> None:
        """Inizializza il sensore."""
        super().__init__(coordinator)
        self._index = sw.index
        self._attr_name = sw.name or f"Presa {sw.index + 1}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_sw_state_{sw.index}"

    @property
    def is_on(self) -> bool | None:
        """Stato corrente della presa."""
        for sw in self.coordinator.data.switches:
            if sw.index == self._index:
                return sw.is_on
        return None
