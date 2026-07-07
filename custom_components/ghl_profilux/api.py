"""Client WebSocket per il controller d'acquario GHL ProfiLux 4/4e.

Protocollo: binario proprietario GHL (reverse-engineered dalla community).
Trasportato su WebSocket ws://<host>/ws con autenticazione HTTP Basic.

Riferimento principale: https://github.com/cjburchell/profilux-go (Apache-2.0).
Implementazione WebSocket Python: https://github.com/fylia32/HA_GHL_PROFILUX

AVVERTENZA: il ProfiLux gestisce male connessioni multiple simultanee.
Non tenere aperto GHL Control Center o l'app GHL Connect mentre questa
integrazione è attiva. Usare una singola istanza del client alla volta.

Frame ENQ (lettura):
  [SOH, SLAVE, MASTER, BCA, STX] + code_nibbles + [ENQ, ETX, BCC, EOT]

Frame command (scrittura):
  [SOH, SLAVE, MASTER, BCA, STX] + code_nibbles + data_nibbles + [ENQ, ETX, BCC, EOT]
  seguito da sendEnd: [SOH, SLAVE, MASTER, BCA, EOT]

Encoding nibble (LSB first):
  - Codici: nibble | 0x40
  - Dati:   nibble | 0x30

Checksum BCA/BCC: sum(bytes) & 0xFF; se < 32, aggiunge 32.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import TYPE_CHECKING

import aiohttp

from .const import (
    MAX_SENSORS,
    MAX_SWITCHES,
    MEGA_BLOCK_SIZE,
    PROTO_ACK,
    PROTO_CODE_OFFSET,
    PROTO_DATA_OFFSET,
    PROTO_ENQ,
    PROTO_EOT,
    PROTO_ETX,
    PROTO_MASTER_ADDR,
    PROTO_NAK,
    PROTO_SLAVE_ADDR,
    PROTO_SOH,
    PROTO_STX,
    CODE_GETSENSORCOUNT,
    CODE_GETSWITCHCOUNT,
    CODE_INVOKESPECIALFUNCTION,
    CODE_ISALARM,
    CODE_PRODUCTID,
    CODE_SENSOR_ACTVALUE_BASE,
    CODE_SENSOR_NAME_BASE,
    CODE_SENSOR_TYPE_BASE,
    CODE_SERIALNUMBER,
    CODE_SOFTWAREVERSION,
    CODE_SP_ALL_CURRENT,
    CODE_SP_STATE_BASE,
    CODE_SWITCH_NAME_BASE,
    CODE_SWITCHPLUG_FUNC_BASE,
    DEVICE_MODE_ALWAYS_OFF,
    DEVICE_MODE_ALWAYS_ON,
    SENSOR_SCALE,
    SENSOR_TYPE_NONE,
    SF_FEED_PAUSE,
    SF_MAINTENANCE,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_RECV_TIMEOUT = 10.0
_CONNECT_TIMEOUT = aiohttp.ClientTimeout(total=15)
_MAX_RECONNECT_DELAY = 60.0


# ── Eccezioni ─────────────────────────────────────────────────────────────────


class ProfiLuxError(Exception):
    """Errore generico del client ProfiLux."""


class ProfiLuxConnectionError(ProfiLuxError):
    """Errore di connessione o WebSocket chiuso."""


class ProfiLuxAuthError(ProfiLuxConnectionError):
    """Credenziali non valide (HTTP 401 durante l'handshake WS)."""


class ProfiLuxProtocolError(ProfiLuxError):
    """Risposta del controller non valida o inattesa."""


# ── Primitivi di framing ───────────────────────────────────────────────────────


def _block_check(data: list[int]) -> int:
    """BCA/BCC: sum & 0xFF, minimo 32 (0x20)."""
    s = sum(data) & 0xFF
    return s if s >= 32 else s + 32


def _encode_code(code: int) -> list[int]:
    """Codifica un numeric code in nibble LSB-first OR-ati con 0x40."""
    nibbles: list[int] = []
    c = code
    while c != 0:
        nibbles.append(PROTO_CODE_OFFSET | (c & 0x0F))
        c >>= 4
    return nibbles


def _encode_data(data: int) -> list[int]:
    """Codifica un valore intero in nibble LSB-first OR-ati con 0x30."""
    if data == 0:
        return [PROTO_DATA_OFFSET]
    # Tratta valori negativi come unsigned 32-bit
    d = data & 0xFFFFFFFF
    nibbles: list[int] = []
    while d != 0:
        nibbles.append(PROTO_DATA_OFFSET | (d & 0x0F))
        d >>= 4
    return nibbles


def make_enquiry(code: int) -> bytes:
    """Costruisce un frame ENQ (lettura) per il codice dato."""
    header = [PROTO_SOH, PROTO_SLAVE_ADDR, PROTO_MASTER_ADDR]
    bca = _block_check(header)
    code_nibbles = _encode_code(code)
    frame = header + [bca, PROTO_STX] + code_nibbles + [PROTO_ENQ, PROTO_ETX]
    bcc = _block_check(frame)
    frame += [bcc, PROTO_EOT]
    return bytes(frame)


def make_command(code: int, data: int) -> tuple[bytes, bytes]:
    """Costruisce il frame di scrittura e il frame di chiusura (sendEnd)."""
    header = [PROTO_SOH, PROTO_SLAVE_ADDR, PROTO_MASTER_ADDR]
    bca = _block_check(header)
    code_nibbles = _encode_code(code)
    data_nibbles = _encode_data(data)
    frame = header + [bca, PROTO_STX] + code_nibbles + data_nibbles + [PROTO_ENQ, PROTO_ETX]
    bcc = _block_check(frame)
    frame += [bcc, PROTO_EOT]

    end_header = [PROTO_SOH, PROTO_SLAVE_ADDR, PROTO_MASTER_ADDR]
    end_bca = _block_check(end_header)
    end_frame = end_header + [end_bca, PROTO_EOT]

    return bytes(frame), bytes(end_frame)


def parse_int_response(data: bytes) -> int | None:
    """Estrae il valore intero da una risposta binaria ProfiLux.

    Restituisce None su risposta malformata o NAK.
    Il valore è signed 16-bit (>= 0x8000 → negativo).
    """
    try:
        stx_pos = data.index(PROTO_STX)
    except ValueError:
        return None

    payload = data[stx_pos + 1:]
    if not payload:
        return None

    # ACK: scrittura andata a buon fine
    if payload[0] == PROTO_ACK:
        return 0

    # NAK: errore controller
    if payload[0] == PROTO_NAK:
        _LOGGER.debug("ProfiLux NAK ricevuto")
        return None

    # Salta i nibble del codice (0x40-0x4F o 0x60-0x6F)
    i = 0
    while i < len(payload):
        b = payload[i]
        if (b & 0xF0) in (0x40, 0x60):
            i += 1
        else:
            break

    # Legge i nibble dei dati (0x30-0x3F), LSB-first
    value = 0
    shift = 0
    while i < len(payload):
        b = payload[i]
        if (b & 0xF0) == PROTO_DATA_OFFSET:
            value |= (b & 0x0F) << shift
            shift += 4
            i += 1
        else:
            break

    # Signed 16-bit
    if value >= 0x8000:
        value -= 0x10000

    return value


def parse_text_response(data: bytes) -> str | None:
    """Estrae una stringa da una risposta binaria ProfiLux.

    Il testo è codificato come coppie di nibble: nibble basso poi nibble alto.
    """
    try:
        stx_pos = data.index(PROTO_STX)
    except ValueError:
        return None

    payload = data[stx_pos + 1:]
    if not payload or payload[0] in (PROTO_ACK, PROTO_NAK):
        return None

    # Salta nibble del codice
    i = 0
    while i < len(payload):
        b = payload[i]
        if (b & 0xF0) in (0x40, 0x60):
            i += 1
        else:
            break

    # Legge coppie di nibble come caratteri ASCII
    chars: list[int] = []
    while i + 1 < len(payload):
        b1, b2 = payload[i], payload[i + 1]
        if (b1 & 0xF0) != PROTO_DATA_OFFSET or (b2 & 0xF0) != PROTO_DATA_OFFSET:
            break
        char_val = (b1 & 0x0F) | ((b2 & 0x0F) << 4)
        if char_val == 0:
            break
        chars.append(char_val)
        i += 2

    if not chars:
        return None
    return bytes(chars).decode("ascii", errors="replace").strip() or None


def parse_ack_response(data: bytes) -> bool:
    """Verifica che la risposta sia un ACK (scrittura riuscita)."""
    try:
        stx_pos = data.index(PROTO_STX)
    except ValueError:
        return False
    payload = data[stx_pos + 1:]
    return bool(payload) and payload[0] == PROTO_ACK


# ── Offset formula ────────────────────────────────────────────────────────────


def sensor_actvalue_code(index: int) -> int:
    """Codice per il valore attuale del sensore i (blocco 8×8, mega-step 1000)."""
    return CODE_SENSOR_ACTVALUE_BASE + (index % 8) * 8 + (index // 8) * MEGA_BLOCK_SIZE


def sensor_type_code(index: int) -> int:
    """Codice per il tipo del sensore i (blocco 8×24)."""
    return CODE_SENSOR_TYPE_BASE + (index % 8) * 24 + (index // 8) * MEGA_BLOCK_SIZE


def sensor_name_code(index: int) -> int:
    """Codice per il nome del sensore i (1 nome = 2 slot EEPROM)."""
    return CODE_SENSOR_NAME_BASE + index * 2


def switch_state_code(index: int) -> int:
    """Codice per lo stato della presa i (SP1_STATE + i)."""
    return CODE_SP_STATE_BASE + index


def switch_func_code(index: int) -> int:
    """Codice per la funzione/modalità della presa i."""
    return CODE_SWITCHPLUG_FUNC_BASE + index


def switch_name_code(index: int) -> int:
    """Codice per il nome della presa i."""
    return CODE_SWITCH_NAME_BASE + index * 2


# ── Client WebSocket ──────────────────────────────────────────────────────────


class ProfiLuxClient:
    """Client per il ProfiLux 4/4e via WebSocket locale.

    Mantiene una singola connessione persistente con riconnessione automatica.
    Tutte le operazioni sono serializzate tramite un asyncio.Lock — il
    controller non tollera richieste concorrenti.
    """

    def __init__(
        self,
        hass: "HomeAssistant",
        host: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Inizializza il client (senza connettere)."""
        self._hass = hass
        self._host = host
        self._username = username
        self._password = password
        self._session = session
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._lock = asyncio.Lock()
        self._reconnect_delay = 1.0

    @property
    def host(self) -> str:
        return self._host

    async def async_connect(self) -> None:
        """Apre la connessione WebSocket (con Basic Auth)."""
        auth = "Basic " + base64.b64encode(
            f"{self._username}:{self._password}".encode()
        ).decode()
        try:
            self._ws = await self._session.ws_connect(
                f"ws://{self._host}/ws",
                headers={"Authorization": auth},
                timeout=_CONNECT_TIMEOUT,
                heartbeat=30,
            )
        except aiohttp.WSServerHandshakeError as err:
            if err.status == 401:
                raise ProfiLuxAuthError(
                    f"Credenziali non valide per il ProfiLux su {self._host}"
                ) from err
            raise ProfiLuxConnectionError(
                f"Handshake WebSocket fallito ({err.status}): {self._host}"
            ) from err
        except (aiohttp.ClientError, OSError, asyncio.TimeoutError) as err:
            raise ProfiLuxConnectionError(
                f"Impossibile connettersi a {self._host}: {err}"
            ) from err
        self._reconnect_delay = 1.0
        _LOGGER.debug("Connesso a ProfiLux ws://%s/ws", self._host)

    async def async_disconnect(self) -> None:
        """Chiude la connessione WebSocket."""
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None

    async def _ensure_connected(self) -> None:
        """Riconnette se la sessione WebSocket è chiusa."""
        if self._ws is None or self._ws.closed:
            _LOGGER.debug(
                "WebSocket non disponibile, tentativo di riconnessione (delay %.1fs)",
                self._reconnect_delay,
            )
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, _MAX_RECONNECT_DELAY)
            await self.async_connect()

    async def _recv(self) -> bytes:
        """Riceve il prossimo frame binario dal WebSocket."""
        assert self._ws is not None
        try:
            msg = await asyncio.wait_for(self._ws.receive(), timeout=_RECV_TIMEOUT)
        except asyncio.TimeoutError as err:
            raise ProfiLuxConnectionError(
                "Timeout in attesa della risposta dal ProfiLux"
            ) from err
        if msg.type == aiohttp.WSMsgType.BINARY:
            return bytes(msg.data)
        if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
            self._ws = None
            raise ProfiLuxConnectionError("WebSocket chiuso dal ProfiLux")
        return b""

    # ── Operazioni di alto livello ────────────────────────────────────────────

    async def async_get_data(self, code: int) -> int:
        """Legge un intero dal controller (ENQ → risposta con valore)."""
        frame = make_enquiry(code)
        async with self._lock:
            await self._ensure_connected()
            assert self._ws is not None
            await self._ws.send_bytes(frame)
            raw = await self._recv()

        value = parse_int_response(raw)
        if value is None:
            raise ProfiLuxProtocolError(
                f"Risposta non valida per code={code}: {raw.hex()}"
            )
        return value

    async def async_get_text(self, code: int) -> str | None:
        """Legge una stringa ASCII dal controller."""
        frame = make_enquiry(code)
        async with self._lock:
            await self._ensure_connected()
            assert self._ws is not None
            await self._ws.send_bytes(frame)
            raw = await self._recv()
        return parse_text_response(raw)

    async def async_send_data(self, code: int, data: int) -> None:
        """Scrive un valore intero nel controller (command + sendEnd + ACK).

        ATTENZIONE: alcuni comandi modificano la EEPROM del controller
        (persistente al riavvio). Verificare il codice prima di usarlo.
        """
        cmd_frame, end_frame = make_command(code, data)
        async with self._lock:
            await self._ensure_connected()
            assert self._ws is not None
            await self._ws.send_bytes(cmd_frame)
            raw = await self._recv()
            if not parse_ack_response(raw):
                _LOGGER.debug(
                    "send_data code=%d data=%d: risposta inattesa %s (continuo)",
                    code,
                    data,
                    raw.hex(),
                )
            await self._ws.send_bytes(end_frame)

    # ── Comandi specifici ─────────────────────────────────────────────────────

    async def async_invoke_feed_pause(self, *, index: int = 0, activate: bool = True) -> None:
        """Attiva o disattiva la pausa alimentazione."""
        arg = (index << 16) | ((0xFF if activate else 0) << 8) | SF_FEED_PAUSE
        await self.async_send_data(CODE_INVOKESPECIALFUNCTION, arg)

    async def async_invoke_maintenance(self, *, index: int = 0, activate: bool = True) -> None:
        """Attiva o disattiva la modalità manutenzione."""
        arg = (index << 16) | ((0xFF if activate else 0) << 8) | SF_MAINTENANCE
        await self.async_send_data(CODE_INVOKESPECIALFUNCTION, arg)

    async def async_set_switch(self, index: int, on: bool) -> None:
        """Imposta la presa index su AlwaysOn (29) o AlwaysOff (30).

        # NOTE: da verificare su hardware reale — scrive in EEPROM.
        Solo le prese già in modalità manuale (AlwaysOn/AlwaysOff) dovrebbero
        essere controllate in questo modo; le altre potrebbero essere in uso
        da timer, automazioni ProfiLux o altri sistemi.
        """
        mode = DEVICE_MODE_ALWAYS_ON if on else DEVICE_MODE_ALWAYS_OFF
        await self.async_send_data(switch_func_code(index), mode)

    # ── Letture batch (usate dal coordinator) ─────────────────────────────────

    async def async_read_system_info(self) -> dict[str, str | int | None]:
        """Legge firmware, seriale e modello del controller."""
        results: dict[str, str | int | None] = {}
        try:
            results["firmware"] = await self.async_get_data(CODE_SOFTWAREVERSION)
        except ProfiLuxError as err:
            _LOGGER.debug("Firmware non leggibile: %s", err)
            results["firmware"] = None
        try:
            results["serial"] = await self.async_get_data(CODE_SERIALNUMBER)
        except ProfiLuxError as err:
            _LOGGER.debug("Seriale non leggibile: %s", err)
            results["serial"] = None
        try:
            results["product_id"] = await self.async_get_data(CODE_PRODUCTID)
        except ProfiLuxError as err:
            _LOGGER.debug("ProductID non leggibile: %s", err)
            results["product_id"] = None
        return results

    async def async_get_sensor_count(self) -> int:
        """Restituisce il numero di sensori segnalati dal controller."""
        try:
            count = await self.async_get_data(CODE_GETSENSORCOUNT)
            return min(max(count, 0), MAX_SENSORS)
        except ProfiLuxError:
            return 4  # fallback sicuro per ProfiLux 4

    async def async_get_switch_count(self) -> int:
        """Restituisce il numero di prese segnalate dal controller."""
        try:
            count = await self.async_get_data(CODE_GETSWITCHCOUNT)
            return min(max(count, 0), MAX_SWITCHES)
        except ProfiLuxError:
            return 6  # fallback sicuro

    async def async_read_sensor(self, index: int) -> dict[str, int | float | None]:
        """Legge tipo e valore di un sensore (None se tipo=0/nessuno)."""
        sensor_type: int | None = None
        value: float | None = None
        try:
            sensor_type = await self.async_get_data(sensor_type_code(index))
        except ProfiLuxError as err:
            _LOGGER.debug("Tipo sensore %d non leggibile: %s", index, err)
        if sensor_type is not None and sensor_type != SENSOR_TYPE_NONE:
            try:
                raw = await self.async_get_data(sensor_actvalue_code(index))
                scale = SENSOR_SCALE.get(sensor_type, 1.0)
                value = round(raw / scale, 2)
            except ProfiLuxError as err:
                _LOGGER.debug("Valore sensore %d non leggibile: %s", index, err)
        return {"type": sensor_type, "value": value}

    async def async_read_switch(self, index: int) -> dict[str, int | None]:
        """Legge stato e funzione di una presa."""
        state: int | None = None
        function: int | None = None
        try:
            state = await self.async_get_data(switch_state_code(index))
        except ProfiLuxError as err:
            _LOGGER.debug("Stato presa %d non leggibile: %s", index, err)
        try:
            function = await self.async_get_data(switch_func_code(index))
        except ProfiLuxError as err:
            _LOGGER.debug("Funzione presa %d non leggibile: %s", index, err)
        return {"state": state, "function": function}

    async def async_read_alarm(self) -> bool | None:
        """Legge lo stato di allarme globale."""
        try:
            val = await self.async_get_data(CODE_ISALARM)
            return val != 0
        except ProfiLuxError:
            return None

    async def async_read_sp_all_current(self) -> int | None:
        """Legge la corrente totale istantanea di tutte le prese (Digital Power Bar / PAB).

        Restituisce il valore grezzo intero dal controller. La scala/unità esatta
        dipende dal firmware: verificare il valore raw contro il display del GHL
        Control Center per determinare il fattore di conversione corretto.
        Ritorna None se il codice non è supportato dal firmware installato.
        """
        try:
            return await self.async_get_data(CODE_SP_ALL_CURRENT)
        except ProfiLuxError as err:
            _LOGGER.debug("SP_ALL_CURRENT non disponibile: %s", err)
            return None
