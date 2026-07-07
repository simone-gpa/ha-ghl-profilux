"""Costanti per l'integrazione GHL ProfiLux."""

from homeassistant.const import Platform

DOMAIN = "ghl_profilux"

# Indirizzo slave ProfiLux e master host (WebSocket)
_SLAVE_ADDR = 0x50  # 80
_MASTER_ADDR = 0x91  # 145 — specifico WebSocket (diverso da TCP/seriale che usa 0x70)

# Byte di controllo protocollo
PROTO_SOH = 0x01
PROTO_STX = 0x02
PROTO_ETX = 0x03
PROTO_EOT = 0x04
PROTO_ENQ = 0x05
PROTO_ACK = 0x06
PROTO_NAK = 0x15
PROTO_DATA_OFFSET = 0x30
PROTO_CODE_OFFSET = 0x40

PROTO_SLAVE_ADDR = _SLAVE_ADDR
PROTO_MASTER_ADDR = _MASTER_ADDR

MEGA_BLOCK_SIZE = 1000  # formula offset: ((i % n) * block) + ((i // n) * 1000)

# ── Codici EEPROM (persistenti) ─────────────────────────────────────────────
CODE_SOFTWAREVERSION = 0
CODE_SOFTWAREDATE = 1
CODE_PRODUCTID = 2
CODE_SERIALNUMBER = 6

CODE_SENSOR_TYPE_BASE = 25       # SENSORPARA1_SENSORTYPE; offset = (i%8)*24 + (i//8)*1000
CODE_SWITCHPLUG_FUNC_BASE = 756  # SWITCHPLUG1_FUNCTION; +1 per ogni presa

CODE_SENSOR_NAME_BASE = 18000    # SENSOR1_NAME; +2 per ogni sensore
CODE_SWITCH_NAME_BASE = 18064    # SWITCHPLUG1_NAME; +2 per ogni presa

# ── Codici volatili (>= 10000) ───────────────────────────────────────────────
CODE_SENSOR_ACTVALUE_BASE = 10000  # SENSORPARA1_ACTVALUE; offset = (i%8)*8 + (i//8)*1000
CODE_SENSOR_ACTSTATE_BASE = 10003  # SENSORPARA1_ACTSTATE; stessa formula
CODE_SP_STATE_BASE = 10100         # SP1_STATE; +1 per ogni presa
CODE_ISALARM = 10090
CODE_OPMODE = 10097
CODE_INVOKESPECIALFUNCTION = 10406

CODE_SP_ALL_CURRENT = 10127  # Corrente totale prese (Digital Power Bar); scala e unità da verificare su HW

CODE_GETSENSORCOUNT = 10500
CODE_GETSWITCHCOUNT = 10501
CODE_GETILLUMINATIONCOUNT = 10510
CODE_GETCURRENTPUMPCOUNT = 10514

# ── Special functions (argomento di INVOKESPECIALFUNCTION) ───────────────────
SF_WATER_CHANGE = 0
SF_MAINTENANCE = 1
SF_FEED_PAUSE = 2
SF_THUNDERSTORM = 3

# Argomento = (index << 16) | (0xFF << 8) | SF_xxx  per attivare
# Argomento = (index << 16) | (0 << 8) | SF_xxx      per disattivare

# ── Modalità switch plug ──────────────────────────────────────────────────────
DEVICE_MODE_ALWAYS_ON = 29
DEVICE_MODE_ALWAYS_OFF = 30

# ── Tipi di sensore ───────────────────────────────────────────────────────────
SENSOR_TYPE_NONE = 0
SENSOR_TYPE_TEMPERATURE = 1
SENSOR_TYPE_PH = 2
SENSOR_TYPE_REDOX = 3
SENSOR_TYPE_FRESHWATER_CONDUCTIVITY = 4
SENSOR_TYPE_CONDUCTIVITY = 5
SENSOR_TYPE_FREE = 6
SENSOR_TYPE_HUMIDITY = 7
SENSOR_TYPE_AIR_TEMPERATURE = 8
SENSOR_TYPE_OXYGEN = 9
SENSOR_TYPE_VOLTAGE = 10

# ── Fattori di scala per tipo sensore ────────────────────────────────────────
SENSOR_SCALE: dict[int, float] = {
    SENSOR_TYPE_TEMPERATURE: 10.0,
    SENSOR_TYPE_PH: 100.0,
    SENSOR_TYPE_REDOX: 1.0,
    SENSOR_TYPE_FRESHWATER_CONDUCTIVITY: 10.0,
    SENSOR_TYPE_CONDUCTIVITY: 10.0,
    SENSOR_TYPE_FREE: 1.0,
    SENSOR_TYPE_HUMIDITY: 10.0,
    SENSOR_TYPE_AIR_TEMPERATURE: 10.0,
    SENSOR_TYPE_OXYGEN: 10.0,
    SENSOR_TYPE_VOLTAGE: 10.0,
    # Tipi estesi osservati su ProfiLux 4e (confermati dall'utente):
    1140: 10.0,  # Conducibilità mS/cm: raw 426 / 10 = 42.6 mS/cm ✓
    3840: 1.0,   # Sonda non attiva (null)
    3843: 1.0,   # Redox mV: raw 36 ≈ 37 mV ✓
}

SENSOR_TYPE_NAMES: dict[int, str] = {
    SENSOR_TYPE_NONE: "None",
    SENSOR_TYPE_TEMPERATURE: "Temperatura",
    SENSOR_TYPE_PH: "pH",
    SENSOR_TYPE_REDOX: "Redox/ORP",
    SENSOR_TYPE_FRESHWATER_CONDUCTIVITY: "Conducibilità dolce",
    SENSOR_TYPE_CONDUCTIVITY: "Conducibilità",
    SENSOR_TYPE_FREE: "Sensore libero",
    SENSOR_TYPE_HUMIDITY: "Umidità",
    SENSOR_TYPE_AIR_TEMPERATURE: "Temperatura aria",
    SENSOR_TYPE_OXYGEN: "Ossigeno",
    SENSOR_TYPE_VOLTAGE: "Tensione",
}

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

DEFAULT_SCAN_INTERVAL = 30
MAX_SENSORS = 32   # ProfiLux 4 supporta fino a 32 sensori
MAX_SWITCHES = 24  # fino a 24 prese controllate
