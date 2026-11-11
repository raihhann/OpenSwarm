"""Decode legacy master commands before executing hardware operations."""

import json

PROTOCOL_VERSION = 1
SEQ_MODULUS = 32767
SEQ_WINDOW = SEQ_MODULUS // 2


def sequence_is_newer(incoming, previous):
    """Independent-node implementation of the master package's wire contract."""
    if isinstance(incoming, bool) or not isinstance(incoming, int) or not 1 <= incoming <= SEQ_MODULUS:
        return False
    return previous <= 0 or 0 < (incoming - previous) % SEQ_MODULUS <= SEQ_WINDOW


def _integer(packet, keys, default=0, minimum=-32768, maximum=32767):
    value = next((packet[key] for key in keys if key in packet), default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError("Invalid command integer")
    return value


def schedule_delay_ms(at_ms, uptime_ms):
    now15 = int(uptime_ms) & 0x7FFF
    return ((int(at_ms) - now15 + 16384) & 0x7FFF) - 16384


def decode_command(data):
    packet = json.loads(data.decode("utf-8"))
    if not isinstance(packet, dict):
        raise ValueError("Expected a JSON object")
    if packet.get("protocol", PROTOCOL_VERSION) != PROTOCOL_VERSION:
        raise ValueError("Unsupported protocol version")
    seq = _integer(packet, ["seq"], minimum=1, maximum=32767) if "seq" in packet else None
    cmd = packet.get("cmd")
    if cmd in ("PING", "STOP"):
        res = {"cmd": cmd}
        if seq is not None:
            res["seq"] = seq
        return res
    if cmd == "PIN":
        res = {"cmd": cmd, "pin": _integer(packet, ["pin"], -1, 0, 254),
               "value": _integer(packet, ["value"], 0, 0, 255),
               "pwm": _integer(packet, ["pwm"], 0, 0, 1)}
        if seq is not None:
            res["seq"] = seq
        return res
    if cmd == "ACT":
        name, payload = packet.get("name"), packet.get("data", "")
        if not isinstance(name, str) or not name or not isinstance(payload, str):
            raise ValueError("Invalid actuator name or payload")
        res = {"cmd": cmd, "name": name, "data": payload,
               "v1": _integer(packet, ["value", "state", "left", "angle", "steps", "reg", "v1"]),
               "v2": _integer(packet, ["right", "val", "v2"])}
        if seq is not None:
            res["seq"] = seq
        if "at_ms" in packet:
            res["at_ms"] = _integer(packet, ["at_ms"], minimum=0, maximum=32767)
        if "lease_ms" in packet:
            res["lease_ms"] = _integer(packet, ["lease_ms"], minimum=1, maximum=30000)
        return res
    raise ValueError("Unknown command")
