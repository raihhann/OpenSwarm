"""Decode legacy master commands before executing hardware operations."""

import json

PROTOCOL_VERSION = 1


def _integer(packet, keys, default=0, minimum=-32768, maximum=32767):
    value = next((packet[key] for key in keys if key in packet), default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError("Invalid command integer")
    return value


def decode_command(data):
    packet = json.loads(data.decode("utf-8"))
    if not isinstance(packet, dict):
        raise ValueError("Expected a JSON object")
    if packet.get("protocol", PROTOCOL_VERSION) != PROTOCOL_VERSION:
        raise ValueError("Unsupported protocol version")
    cmd = packet.get("cmd")
    if cmd in ("PING", "STOP"):
        return {"cmd": cmd}
    if cmd == "PIN":
        return {"cmd": cmd, "pin": _integer(packet, ["pin"], -1, 0, 254),
                "value": _integer(packet, ["value"], 0, 0, 255),
                "pwm": _integer(packet, ["pwm"], 0, 0, 1)}
    if cmd == "ACT":
        name, payload = packet.get("name"), packet.get("data", "")
        if not isinstance(name, str) or not name or not isinstance(payload, str):
            raise ValueError("Invalid actuator name or payload")
        return {"cmd": cmd, "name": name, "data": payload,
                "v1": _integer(packet, ["value", "state", "left", "angle", "steps", "reg", "v1"]),
                "v2": _integer(packet, ["right", "val", "v2"])}
    raise ValueError("Unknown command")
