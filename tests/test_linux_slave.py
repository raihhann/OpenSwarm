import json
import socket
import unittest

from openswarm import SwarmMaster
from openswarm_slave import SwarmNode
from openswarm_slave.hal_linux import LinuxHAL
from openswarm_slave.protocol import decode_command


class FakeSocket:
    def __init__(self, packet):
        self.packet = packet
        self.sent = []

    def recvfrom(self, count):
        return self.packet, ("127.0.0.1", 40000)

    def sendto(self, packet, address):
        self.sent.append(json.loads(packet))


class SlaveTests(unittest.TestCase):
    def node(self):
        return SwarmNode("test", udp_port=0, hal=LinuxHAL(verbose_sim=False, backend="sim"))

    def test_malformed_commands_leave_session_unchanged(self):
        node = self.node()
        for packet in [b'[]', b'null', b'\xff', b'{"cmd":"UNKNOWN"}',
                       b'{"cmd":"PIN","pin":"bad"}',
                       b'{"cmd":"ACT","name":[],"value":1}',
                       b'{"cmd":"ACT","name":"led","value":1e309}',
                       b'{"cmd":"ACT","name":"led","value":40000}']:
            node._sock = FakeSocket(packet)
            node._handle_incoming()
            self.assertIsNone(node._master_addr)

    def test_legacy_actuator_fields_and_escaped_payload(self):
        for fields in [{"value": 12}, {"left": 12}, {"angle": 12}, {"v1": 12}, {"reg": 12}]:
            packet = decode_command(json.dumps({"cmd": "ACT", "name": "x", **fields}).encode())
            self.assertEqual(packet["v1"], 12)
        text = 'hello "robot"\\path'
        packet = decode_command(json.dumps({"cmd": "ACT", "name": "x", "data": text}).encode())
        self.assertEqual(packet["data"], text)

    def test_sensor_failure_is_omitted_and_recovers(self):
        node = self.node()
        node._master_addr = ("127.0.0.1", 40000)
        node._sock = FakeSocket(b'{}')
        def broken():
            raise RuntimeError("disconnected")
        node.register_custom_sensor("bad", broken)
        node.register_custom_sensor("good", lambda: [1, 2])
        node._send_telemetry()
        self.assertEqual(node._sock.sent[-1]["sensors"], {"good": [1, 2]})
        self.assertIn("bad", node._sock.sent[-1]["sensor_errors"])
        node.register_custom_sensor("bad", lambda: 4)
        node._send_telemetry()
        self.assertEqual(node._sock.sent[-1]["sensor_errors"], {})

    def test_nonfinite_sensor_output_does_not_poison_packet(self):
        node = self.node()
        node._master_addr = ("127.0.0.1", 40000)
        node._sock = FakeSocket(b'{}')
        node.register_custom_sensor("bad", lambda: float("nan"))
        node._send_telemetry()
        self.assertNotIn("bad", node._sock.sent[-1]["sensors"])

    def test_unsupported_stepper_is_explicit(self):
        with self.assertRaises(NotImplementedError):
            self.node().register_stepper("step", 2, 3)

    def test_sysfs_cannot_claim_pwm_or_servo_success(self):
        hal = LinuxHAL(verbose_sim=False, backend="sim")
        hal._gpio_backend = "sysfs"
        for operation in [hal.pwm_write, hal.servo_write]:
            with self.assertRaises(NotImplementedError):
                operation(2, 90)
        self.assertEqual(hal._sim_pins, {})

    def test_loopback_master_and_slave_survive_invalid_udp(self):
        node = self.node()
        node.register_digital_output("led", 2)
        node.register_custom_sensor("count", lambda: 42)
        # Keep this integration check strictly on loopback, including discovery.
        node.hal.broadcast_ip = lambda: "127.0.0.1"
        node.start(block=False)
        self.addCleanup(node.stop)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(b'[]', ("127.0.0.1", node.udp_port))
        with SwarmMaster(discovery_port=0) as master:
            remote = master.connect("test", ip="127.0.0.1", port=node.udp_port, timeout=1)
            self.assertEqual(remote.read("count"), 42)
            remote.digital_write("led", 1)
            self.assertTrue(node._thread.is_alive())
        node.stop()
        self.assertFalse(node._thread.is_alive())
