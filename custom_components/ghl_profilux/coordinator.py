"""Coordinator per l'integrazione GHL ProfiLux."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import ProfiLuxClient, ProfiLuxConnectionError, ProfiLuxError, sensor_name_code
from .const import DEFAULT_SCAN_INTERVAL, DEVICE_MODE_ALWAYS_OFF, DEVICE_MODE_ALWAYS_ON, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class SensorData:
    """Stato di un sensore ProfiLux."""

    index: int
    sensor_type: int  # tipo GHL (1=temp, 2=pH, ecc.)
    value: float | None = None
    name: str | None = None


@dataclass
class SwitchData:
    """Stato di una presa ProfiLux."""

    index: int
    state: int | None = None  # 0=off, non-0=on (da verificare su hw reale)
    function: int | None = None  # DeviceMode
    name: str | None = None

    @property
    def is_on(self) -> bool | None:
        if self.state is None:
            return None
        return self.state != 0

    @property
    def is_manual(self) -> bool:
        """Presa in modalità manuale (AlwaysOn/AlwaysOff), controllabile via HA."""
        return self.function in (DEVICE_MODE_ALWAYS_ON, DEVICE_MODE_ALWAYS_OFF)


@dataclass
class ProfiLuxData:
    """Snapshot completo dello stato del controller."""

    sensors: list[SensorData] = field(default_factory=list)
    switches: list[SwitchData] = field(default_factory=list)
    alarm: bool | None = None
    firmware: int | None = None
    serial: int | None = None
    product_id: int | None = None
    sp_all_current_raw: int | None = None  # corrente totale prese, valore grezzo (unità da verificare su HW)


class ProfiLuxCoordinator(DataUpdateCoordinator[ProfiLuxData]):
    """Coordinator: polling periodico di un singolo controller ProfiLux."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ProfiLuxClient,
    ) -> None:
        """Inizializza il coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.host}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self._system_info_read = False
        # Numero di sensori/prese, rilevato al primo refresh
        self._sensor_count: int | None = None
        self._switch_count: int | None = None
        # Nomi letti una sola volta (cambiano raramente)
        self._sensor_names: dict[int, str | None] = {}
        self._names_read = False

    @property
    def device_info(self) -> DeviceInfo:
        """DeviceInfo del controller (usato da tutte le entità)."""
        data = self.data
        serial = str(data.serial) if data and data.serial else self.client.host
        fw_str = str(data.firmware) if data and data.firmware else None
        product_map = {
            4: "ProfiLux 4",
            5: "ProfiLux 4e",
            6: "ProfiLux Mini",
            23: "ProfiLux 4e",  # variante firmware osservata
        }
        pid = data.product_id if data else None
        model = product_map.get(pid, f"ProfiLux (id:{pid})") if pid else "ProfiLux"
        return DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer="GHL",
            model=model,
            name=f"GHL ProfiLux ({self.client.host})",
            serial_number=serial if data and data.serial else None,
            sw_version=fw_str,
            configuration_url=f"http://{self.client.host}",
        )

    async def _async_update_data(self) -> ProfiLuxData:
        try:
            return await self._fetch()
        except ProfiLuxConnectionError as err:
            raise UpdateFailed(f"Connessione al ProfiLux persa: {err}") from err
        except ProfiLuxError as err:
            raise UpdateFailed(str(err)) from err

    async def _fetch(self) -> ProfiLuxData:
        client = self.client
        result = ProfiLuxData()

        # Info di sistema: lette una sola volta
        if not self._system_info_read:
            try:
                info = await client.async_read_system_info()
                result.firmware = info.get("firmware")
                result.serial = info.get("serial")
                result.product_id = info.get("product_id")
                self._system_info_read = True
            except ProfiLuxError as err:
                _LOGGER.debug("Info sistema non disponibili: %s", err)
        else:
            # Mantieni i valori precedenti
            if self.data:
                result.firmware = self.data.firmware
                result.serial = self.data.serial
                result.product_id = self.data.product_id

        # Numero di sensori/prese: rilevato una volta, poi fisso
        if self._sensor_count is None:
            self._sensor_count = await client.async_get_sensor_count()
            _LOGGER.debug("Sensori rilevati: %d", self._sensor_count)
        if self._switch_count is None:
            self._switch_count = await client.async_get_switch_count()
            _LOGGER.debug("Prese rilevate: %d", self._switch_count)

        # Allarme globale
        result.alarm = await client.async_read_alarm()

        # Nomi sensori: letti una sola volta (costosi in termini di round-trip)
        if not self._names_read:
            for i in range(self._sensor_count):
                try:
                    name = await client.async_get_text(sensor_name_code(i))
                except ProfiLuxError:
                    name = None
                self._sensor_names[i] = name
            self._names_read = True
            _LOGGER.debug("Nomi sensori letti: %s", self._sensor_names)

        # Sensori
        for i in range(self._sensor_count):
            sensor_raw = await client.async_read_sensor(i)
            sensor_type = sensor_raw.get("type")
            if sensor_type is None or sensor_type == 0:
                continue  # slot vuoto
            result.sensors.append(
                SensorData(
                    index=i,
                    sensor_type=sensor_type,
                    value=sensor_raw.get("value"),
                    name=self._sensor_names.get(i),
                )
            )

        # Prese
        for i in range(self._switch_count):
            sw_raw = await client.async_read_switch(i)
            result.switches.append(
                SwitchData(
                    index=i,
                    state=sw_raw.get("state"),
                    function=sw_raw.get("function"),
                )
            )

        # Corrente totale prese (Digital Power Bar / PAB)
        raw = await client.async_read_sp_all_current()
        if raw is not None:
            _LOGGER.debug("SP_ALL_CURRENT raw=%d (confrontare con GHL Control Center per scala)", raw)
        result.sp_all_current_raw = raw

        return result


class ProfiLuxEntity(CoordinatorEntity[ProfiLuxCoordinator]):
    """Entità base legata al coordinator ProfiLux."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ProfiLuxCoordinator) -> None:
        """Inizializza con il DeviceInfo del controller."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
