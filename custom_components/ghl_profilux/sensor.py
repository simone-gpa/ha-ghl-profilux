"""Sensori per GHL ProfiLux: sonde (pH, temperatura, redox, conducibilità, …)."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import ProfiLuxConfigEntry
from .const import (
    SENSOR_TYPE_AIR_TEMPERATURE,
    SENSOR_TYPE_CONDUCTIVITY,
    SENSOR_TYPE_FRESHWATER_CONDUCTIVITY,
    SENSOR_TYPE_HUMIDITY,
    SENSOR_TYPE_OXYGEN,
    SENSOR_TYPE_PAB_MEAS,
    SENSOR_TYPE_PAB_MEAS_ACTIVE,
    SENSOR_TYPE_PAB_POWER,
    SENSOR_TYPE_PH,
    SENSOR_TYPE_REDOX,
    SENSOR_TYPE_TEMPERATURE,
    SENSOR_TYPE_VOLTAGE,
)
from .coordinator import ProfiLuxCoordinator, ProfiLuxEntity, SensorData

# Mappa tipo_sensore → (device_class, unit, state_class, icon)
_SENSOR_META: dict[
    int,
    tuple[SensorDeviceClass | None, str | None, SensorStateClass | None, str | None],
] = {
    SENSOR_TYPE_TEMPERATURE: (
        SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        SensorStateClass.MEASUREMENT,
        None,
    ),
    SENSOR_TYPE_AIR_TEMPERATURE: (
        SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        SensorStateClass.MEASUREMENT,
        None,
    ),
    SENSOR_TYPE_PH: (
        None,
        "pH",
        SensorStateClass.MEASUREMENT,
        "mdi:ph",
    ),
    SENSOR_TYPE_REDOX: (
        None,
        UnitOfElectricPotential.MILLIVOLT,
        SensorStateClass.MEASUREMENT,
        "mdi:flash",
    ),
    SENSOR_TYPE_FRESHWATER_CONDUCTIVITY: (
        SensorDeviceClass.CONDUCTIVITY,
        "µS/cm",
        SensorStateClass.MEASUREMENT,
        None,
    ),
    SENSOR_TYPE_CONDUCTIVITY: (
        SensorDeviceClass.CONDUCTIVITY,
        "µS/cm",
        SensorStateClass.MEASUREMENT,
        None,
    ),
    SENSOR_TYPE_HUMIDITY: (
        SensorDeviceClass.HUMIDITY,
        "%",
        SensorStateClass.MEASUREMENT,
        None,
    ),
    SENSOR_TYPE_OXYGEN: (
        None,
        "mg/L",
        SensorStateClass.MEASUREMENT,
        "mdi:fish",
    ),
    SENSOR_TYPE_VOLTAGE: (
        SensorDeviceClass.VOLTAGE,
        UnitOfElectricPotential.VOLT,
        SensorStateClass.MEASUREMENT,
        None,
    ),
    # Tipi PAB (Digital Power Bar) — scala da verificare contro GHL Control Center
    SENSOR_TYPE_PAB_POWER: (
        SensorDeviceClass.POWER,
        UnitOfPower.WATT,
        SensorStateClass.MEASUREMENT,
        "mdi:lightning-bolt",
    ),
    SENSOR_TYPE_PAB_MEAS: (
        None,
        None,
        SensorStateClass.MEASUREMENT,
        "mdi:current-ac",
    ),
    SENSOR_TYPE_PAB_MEAS_ACTIVE: (
        None,
        None,
        SensorStateClass.MEASUREMENT,
        "mdi:current-ac",
    ),
}

_SENSOR_TYPE_NAMES: dict[int, str] = {
    SENSOR_TYPE_TEMPERATURE: "Temperatura",
    SENSOR_TYPE_AIR_TEMPERATURE: "Temperatura aria",
    SENSOR_TYPE_PH: "pH",
    SENSOR_TYPE_REDOX: "Redox",
    SENSOR_TYPE_FRESHWATER_CONDUCTIVITY: "Conducibilità",
    SENSOR_TYPE_CONDUCTIVITY: "Conducibilità",
    SENSOR_TYPE_HUMIDITY: "Umidità",
    SENSOR_TYPE_OXYGEN: "Ossigeno",
    SENSOR_TYPE_VOLTAGE: "Tensione",
    SENSOR_TYPE_PAB_POWER: "Potenza PAB",
    SENSOR_TYPE_PAB_MEAS: "Misura PAB",
    SENSOR_TYPE_PAB_MEAS_ACTIVE: "Misura PAB",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProfiLuxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea un sensore HA per ogni sonda attiva rilevata dal ProfiLux."""
    coordinator = entry.runtime_data
    entities = [
        ProfiLuxSensor(coordinator, sensor)
        for sensor in coordinator.data.sensors
        if sensor.sensor_type in _SENSOR_META
    ]
    # Sensori di tipo non mappato: entità generica senza device_class
    for sensor in coordinator.data.sensors:
        if sensor.sensor_type not in _SENSOR_META:
            entities.append(ProfiLuxSensor(coordinator, sensor))
    # Corrente totale prese (Digital Power Bar / PAB) — sempre presente
    entities.append(ProfiLuxTotalCurrentSensor(coordinator))
    async_add_entities(entities)


class ProfiLuxSensor(ProfiLuxEntity, SensorEntity):
    """Sensore ProfiLux — un'entità per ogni sonda attiva sul controller."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ProfiLuxCoordinator, sensor: SensorData) -> None:
        """Inizializza il sensore."""
        super().__init__(coordinator)
        self._index = sensor.index
        self._sensor_type = sensor.sensor_type

        # DeviceClass, unità e icona in base al tipo
        meta = _SENSOR_META.get(sensor.sensor_type)
        if meta:
            dc, unit, sc, icon = meta
            self._attr_device_class = dc
            self._attr_native_unit_of_measurement = unit
            self._attr_state_class = sc
            if icon:
                self._attr_icon = icon
        else:
            self._attr_native_unit_of_measurement = None

        type_name = _SENSOR_TYPE_NAMES.get(sensor.sensor_type, f"Sensore {sensor.sensor_type}")
        # Slot 1-based per l'utente
        self._attr_name = f"{type_name} (slot {sensor.index + 1})"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_sensor_{sensor.index}"
        self._attr_suggested_display_precision = 1

    @property
    def native_value(self) -> StateType:
        """Valore corrente della sonda."""
        for s in self.coordinator.data.sensors:
            if s.index == self._index:
                return s.value
        return None


class ProfiLuxTotalCurrentSensor(ProfiLuxEntity, SensorEntity):
    """Corrente totale istantanea di tutte le prese (Digital Power Bar / PAB).

    Il protocollo WebSocket GHL espone solo il totale aggregato (SP_ALL_CURRENT,
    codice 10127) — non sono disponibili valori per singola presa.
    La scala esatta del valore raw dipende dal firmware; verificare il valore
    'raw' negli attributi aggiuntivi confrontandolo con GHL Control Center.
    """

    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_suggested_display_precision = 1
    _attr_name = "Corrente totale prese"

    # Scala provvisoria: raw / 10 = A (comune nel protocollo GHL).
    # Se il valore non corrisponde al display di GHL Control Center,
    # verificare il raw negli attributi aggiuntivi e correggere qui.
    _SCALE = 10.0

    def __init__(self, coordinator: ProfiLuxCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_sp_all_current"

    @property
    def native_value(self) -> StateType:
        raw = self.coordinator.data.sp_all_current_raw
        if raw is None:
            return None
        return round(raw / self._SCALE, 1)

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        return {"raw": self.coordinator.data.sp_all_current_raw}
