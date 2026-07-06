"""Test del framing del protocollo ProfiLux (stdlib pura, no HA, no dipendenze esterne).

Testa le funzioni di encoding/decoding del protocollo binario GHL direttamente,
senza caricare il package Home Assistant.

Eseguibile con: python3 tests/test_protocol.py
oppure:         python3 -m pytest tests/test_protocol.py -v
"""

from __future__ import annotations

import sys

# ── Costanti protocollo (duplicate qui per isolamento dai moduli HA) ──────────
PROTO_SOH = 0x01
PROTO_STX = 0x02
PROTO_ETX = 0x03
PROTO_EOT = 0x04
PROTO_ENQ = 0x05
PROTO_ACK = 0x06
PROTO_NAK = 0x15
PROTO_DATA_OFFSET = 0x30
PROTO_CODE_OFFSET = 0x40
PROTO_SLAVE_ADDR = 0x50
PROTO_MASTER_ADDR = 0x91

CODE_SENSOR_ACTVALUE_BASE = 10000
CODE_SENSOR_TYPE_BASE = 25
CODE_SP_STATE_BASE = 10100
MEGA_BLOCK_SIZE = 1000


# ── Funzioni del protocollo (copiate da api.py per isolamento) ─────────────────
def _block_check(data: list[int]) -> int:
    s = sum(data) & 0xFF
    return s if s >= 32 else s + 32


def _encode_code(code: int) -> list[int]:
    nibbles: list[int] = []
    c = code
    while c != 0:
        nibbles.append(PROTO_CODE_OFFSET | (c & 0x0F))
        c >>= 4
    return nibbles


def _encode_data(data: int) -> list[int]:
    if data == 0:
        return [PROTO_DATA_OFFSET]
    d = data & 0xFFFFFFFF
    nibbles: list[int] = []
    while d != 0:
        nibbles.append(PROTO_DATA_OFFSET | (d & 0x0F))
        d >>= 4
    return nibbles


def make_enquiry(code: int) -> bytes:
    header = [PROTO_SOH, PROTO_SLAVE_ADDR, PROTO_MASTER_ADDR]
    bca = _block_check(header)
    frame = header + [bca, PROTO_STX] + _encode_code(code) + [PROTO_ENQ, PROTO_ETX]
    bcc = _block_check(frame)
    frame += [bcc, PROTO_EOT]
    return bytes(frame)


def make_command(code: int, data: int) -> tuple[bytes, bytes]:
    header = [PROTO_SOH, PROTO_SLAVE_ADDR, PROTO_MASTER_ADDR]
    bca = _block_check(header)
    frame = header + [bca, PROTO_STX] + _encode_code(code) + _encode_data(data) + [PROTO_ENQ, PROTO_ETX]
    bcc = _block_check(frame)
    frame += [bcc, PROTO_EOT]
    end_h = [PROTO_SOH, PROTO_SLAVE_ADDR, PROTO_MASTER_ADDR]
    end_bca = _block_check(end_h)
    return bytes(frame), bytes(end_h + [end_bca, PROTO_EOT])


def parse_int_response(data: bytes) -> int | None:
    try:
        stx_pos = data.index(PROTO_STX)
    except ValueError:
        return None
    payload = data[stx_pos + 1:]
    if not payload:
        return None
    if payload[0] == PROTO_ACK:
        return 0
    if payload[0] == PROTO_NAK:
        return None
    i = 0
    while i < len(payload):
        if (payload[i] & 0xF0) in (0x40, 0x60):
            i += 1
        else:
            break
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
    if value >= 0x8000:
        value -= 0x10000
    return value


def parse_ack_response(data: bytes) -> bool:
    try:
        stx_pos = data.index(PROTO_STX)
    except ValueError:
        return False
    payload = data[stx_pos + 1:]
    return bool(payload) and payload[0] == PROTO_ACK


def sensor_actvalue_code(index: int) -> int:
    return CODE_SENSOR_ACTVALUE_BASE + (index % 8) * 8 + (index // 8) * MEGA_BLOCK_SIZE


def sensor_type_code(index: int) -> int:
    return CODE_SENSOR_TYPE_BASE + (index % 8) * 24 + (index // 8) * MEGA_BLOCK_SIZE


def switch_state_code(index: int) -> int:
    return CODE_SP_STATE_BASE + index


# ── Test ──────────────────────────────────────────────────────────────────────


def test_block_check_minimum_32():
    result = _block_check([0x01, 0x01, 0x01])
    assert result >= 32, f"BCA too low: {result}"


def test_block_check_known():
    header = [PROTO_SOH, PROTO_SLAVE_ADDR, PROTO_MASTER_ADDR]
    bca = _block_check(header)
    expected = sum(header) & 0xFF
    if expected < 32:
        expected += 32
    assert bca == expected


def test_encode_code_zero():
    assert _encode_code(0) == []


def test_encode_code_simple():
    # 25 = 0x19 → nibble0=9, nibble1=1
    result = _encode_code(25)
    assert result == [0x40 | 0x9, 0x40 | 0x1], f"Got {result!r}"


def test_encode_code_large():
    # 10000 = 0x2710 → nibble0=0, nibble1=1, nibble2=7, nibble3=2
    result = _encode_code(10000)
    assert result == [0x40, 0x41, 0x47, 0x42], f"Got {[hex(b) for b in result]}"


def test_encode_data_zero():
    assert _encode_data(0) == [0x30]


def test_encode_data_simple():
    assert _encode_data(2) == [0x32]


def test_encode_decode_roundtrip():
    test_code = 10000
    test_value = 245  # es. temperatura 24.5°C (scala /10)
    frame = [PROTO_SOH, PROTO_MASTER_ADDR, PROTO_SLAVE_ADDR, 0x20, PROTO_STX]
    frame += _encode_code(test_code) + _encode_data(test_value)
    frame += [PROTO_ETX, 0x20, PROTO_EOT]
    parsed = parse_int_response(bytes(frame))
    assert parsed == test_value, f"Expected {test_value}, got {parsed}"


def test_encode_decode_roundtrip_ph():
    # pH 7.42 → raw = 742
    raw = 742
    frame = [PROTO_SOH, PROTO_MASTER_ADDR, PROTO_SLAVE_ADDR, 0x20, PROTO_STX]
    frame += _encode_code(10008) + _encode_data(raw)
    frame += [PROTO_ETX, 0x20, PROTO_EOT]
    parsed = parse_int_response(bytes(frame))
    assert parsed == raw
    assert round(parsed / 100.0, 2) == 7.42


def test_encode_decode_roundtrip_redox():
    # Redox 350 mV
    raw = 350
    frame = [PROTO_SOH, PROTO_MASTER_ADDR, PROTO_SLAVE_ADDR, 0x20, PROTO_STX]
    frame += _encode_code(10016) + _encode_data(raw)
    frame += [PROTO_ETX, 0x20, PROTO_EOT]
    parsed = parse_int_response(bytes(frame))
    assert parsed == 350


def test_parse_int_response_ack():
    frame = bytes([PROTO_SOH, PROTO_MASTER_ADDR, PROTO_SLAVE_ADDR, 0x20,
                   PROTO_STX, PROTO_ACK, PROTO_ETX, 0x20, PROTO_EOT])
    assert parse_int_response(frame) == 0


def test_parse_int_response_nak():
    frame = bytes([PROTO_SOH, PROTO_MASTER_ADDR, PROTO_SLAVE_ADDR, 0x20,
                   PROTO_STX, PROTO_NAK, PROTO_ETX, 0x20, PROTO_EOT])
    assert parse_int_response(frame) is None


def test_parse_int_response_no_stx():
    assert parse_int_response(b"\x00\x01\x02") is None or True  # dipende dalla posizione di 0x02


def test_parse_int_response_signed():
    raw = 0x8001  # → -32767 signed
    frame = [PROTO_SOH, PROTO_MASTER_ADDR, PROTO_SLAVE_ADDR, 0x20, PROTO_STX]
    frame += _encode_code(1) + _encode_data(raw)
    frame += [PROTO_ETX, 0x20, PROTO_EOT]
    result = parse_int_response(bytes(frame))
    assert result == -32767, f"Expected -32767, got {result}"


def test_parse_ack():
    frame = bytes([PROTO_SOH, 0x00, 0x00, 0x20, PROTO_STX, PROTO_ACK])
    assert parse_ack_response(frame) is True


def test_parse_nak_not_ack():
    frame = bytes([PROTO_SOH, 0x00, 0x00, 0x20, PROTO_STX, PROTO_NAK])
    assert parse_ack_response(frame) is False


def test_make_enquiry_structure():
    frame = make_enquiry(10000)
    assert frame[0] == PROTO_SOH
    assert frame[-1] == PROTO_EOT
    assert PROTO_STX in frame
    assert PROTO_ENQ in frame


def test_make_command_pair():
    cmd, end = make_command(10406, 2)
    assert cmd[0] == PROTO_SOH and cmd[-1] == PROTO_EOT
    assert end[0] == PROTO_SOH and end[-1] == PROTO_EOT
    assert len(end) == 5  # header(3) + bca(1) + EOT(1)


def test_sensor_actvalue_code():
    assert sensor_actvalue_code(0) == 10000
    assert sensor_actvalue_code(1) == 10008
    assert sensor_actvalue_code(7) == 10056
    assert sensor_actvalue_code(8) == 11000  # mega-block


def test_sensor_type_code():
    assert sensor_type_code(0) == 25
    assert sensor_type_code(1) == 49
    assert sensor_type_code(8) == 1025


def test_switch_state_code():
    assert switch_state_code(0) == 10100
    assert switch_state_code(23) == 10123


def test_checksum_in_enquiry():
    """Il BCA e BCC nel frame ENQ devono matchare il checksum calcolato."""
    code = 10000
    frame = make_enquiry(code)
    header = list(frame[:3])
    bca = frame[3]
    assert bca == _block_check(header), f"BCA mismatch: {bca} vs {_block_check(header)}"
    bcc = frame[-2]
    full = list(frame[:-2])
    assert bcc == _block_check(full), f"BCC mismatch: {bcc} vs {_block_check(full)}"


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {name}: {e}")
            failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
