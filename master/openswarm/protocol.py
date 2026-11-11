"""Validation for the dependency-free OpenSwarm UDP transport.

Legacy packets without a version remain supported. Unknown additive fields are
ignored so nodes and masters can be upgraded independently.
"""

import ipaddress
import json
import math

PROTOCOL_VERSION = 1
MAX_DATAGRAM_BYTES = 4096
SEQ_MODULUS = 32767
SEQ_WINDOW = SEQ_MODULUS // 2


def sequence_is_newer(incoming, previous):
    """Strict ordering on 1..32767; zero denotes an empty session.

    Comparisons require less than half a cycle of separation. Control messages
    never authorize a rewind/reset of this watermark.
    """
    if isinstance(incoming, bool) or not isinstance(incoming, int) or not 1 <= incoming <= SEQ_MODULUS:
        return False
    return previous <= 0 or 0 < (incoming - previous) % SEQ_MODULUS <= SEQ_WINDOW


def integer(value, minimum=0, maximum=2**63 - 1):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a numeric integer")
    if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
        raise ValueError("Expected a finite integer")
    if not minimum <= value <= maximum:
        raise ValueError("Integer outside supported range")
    return int(value)


def sensor_values(values):
    if not isinstance(values, dict):
        raise ValueError("Sensors must be an object")
    for name, value in values.items():
        if not isinstance(name, str) or not name:
            raise ValueError("Sensor names must be nonempty strings")
        components = value if isinstance(value, list) else [value]
        if not 1 <= len(components) <= 6:
            raise ValueError("Sensors must contain one to six values")
        for component in components:
            if (isinstance(component, bool) or not isinstance(component, (int, float))
                    or not math.isfinite(component)):
                raise ValueError("Sensor values must be finite numbers")
    return values


def decode_packet(data):
    if len(data) > MAX_DATAGRAM_BYTES:
        raise ValueError("Datagram too large")
    packet = json.loads(data.decode("utf-8"))
    if not isinstance(packet, dict):
        raise ValueError("Expected a JSON object")
    if packet.get("protocol", PROTOCOL_VERSION) != PROTOCOL_VERSION:
        raise ValueError("Unsupported protocol version")
    return packet


def source_ip(address):
    """Use the transport source; advertised addresses can belong to another NIC."""
    return str(ipaddress.IPv4Address(address))
