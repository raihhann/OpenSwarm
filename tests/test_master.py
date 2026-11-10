import json
import socket
import threading
import time
import unittest
from unittest.mock import patch

from openswarm import RemoteSwarmNode, SwarmMaster
from openswarm.protocol import decode_packet


class MasterTests(unittest.TestCase):
    def setUp(self):
        self.master = SwarmMaster(discovery_port=0)
        self.addCleanup(self.master.close)

    def hello(self, node="robot", port=4210):
        self.master._handle_packet(json.dumps({"type": "HELLO", "node": node,
            "board": "TEST", "port": port, "ip": "192.0.2.99"}).encode(), ("127.0.0.1", port))

    def test_discovery_and_shutdown_are_passive(self):
        with patch.object(self.master, "_send_json") as send:
            self.hello()
            time.sleep(0.02)
            self.assertTrue(self.master.get("robot").is_online)
            self.assertEqual(self.master.get("robot").ip, "127.0.0.1")
            self.master.close()
            send.assert_not_called()

    def test_active_shutdown_stops_only_subscribed_nodes(self):
        with patch.object(self.master, "_send_json") as send:
            self.hello("active")
            self.hello("observer")
            self.master.subscribe("active")
            self.master.close()
            stops = [call for call in send.call_args_list if call.args[2]["cmd"] == "STOP"]
            self.assertEqual(len(stops), 1)
            self.assertFalse(self.master._rx_thread.is_alive())
            self.assertFalse(self.master._hb_thread.is_alive())

    def test_direct_connect_times_out_without_telemetry(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as offline:
            offline.bind(("127.0.0.1", 0))
            with self.assertRaises(TimeoutError):
                self.master.connect("missing", ip="127.0.0.1", port=offline.getsockname()[1], timeout=0.08)
        self.assertFalse(self.master.get("missing").is_online)
        self.assertNotIn("missing", self.master._active_nodes)

    def test_direct_connect_verifies_identity_and_state(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as slave:
            slave.bind(("127.0.0.1", 0))
            slave.settimeout(1)
            def reply():
                _, address = slave.recvfrom(1024)
                slave.sendto(b'{"type":"STATE","node":"robot","sensors":{"distance":12}}', address)
            thread = threading.Thread(target=reply)
            thread.start()
            node = self.master.connect("robot", ip="127.0.0.1", port=slave.getsockname()[1], timeout=1)
            thread.join(1)
            self.assertEqual(node.read("distance"), 12)
            self.assertTrue(node.is_online)

    def test_invalid_packets_do_not_create_nodes(self):
        for packet in [b'[]', b'null', b'{}', b'\xff',
                       b'{"type":"STATE","node":"x","uptime_ms":1e309}',
                       b'{"type":"STATE","node":"x","port":true}',
                       b'{"type":"STATE","node":"x","sensors":{"x":NaN}}',
                       b'{"type":"HELLO","node":"x","protocol":2}']:
            self.master._handle_packet(packet, ("127.0.0.1", 4210))
        self.assertEqual(self.master.nodes, {})

    def test_state_from_another_endpoint_is_ignored(self):
        self.hello()
        packet = b'{"type":"STATE","node":"robot","sensors":{"x":12}}'
        self.master._handle_packet(packet, ("127.0.0.1", 4212))
        self.assertEqual(self.master.get("robot").sensors, {})
        self.master._handle_packet(packet, ("127.0.0.1", 4210))
        self.assertEqual(self.master.get("robot").read("x"), 12)

    def test_node_freshness_is_monotonic_and_snapshots_are_isolated(self):
        node = RemoteSwarmNode("x", "127.0.0.1", 4210, lambda *a: None)
        self.assertFalse(node.is_online)
        node._update_state(1, {"imu": [1, 2, 3]})
        snapshot = node.sensors
        snapshot["imu"][0] = 99
        self.assertEqual(node.read("imu"), [1, 2, 3])
        with patch("openswarm.node.time.time", return_value=-100000):
            self.assertTrue(node.is_online)
            self.assertGreaterEqual(node.telemetry_age, 0)
        node._telemetry_at -= 3
        self.assertIsNone(node.read("imu", None, max_age=1))

    def test_complete_samples_clear_missing_sensors_and_expose_faults(self):
        self.hello()
        for sensors, errors in [({"x": 1}, {}), ({}, {"x": "unavailable"})]:
            self.master._handle_packet(json.dumps({"type": "STATE", "node": "robot", "sensors": sensors,
                "sensor_errors": errors}).encode(), ("127.0.0.1", 4210))
        self.assertEqual(self.master.get("robot").sensors, {})
        self.assertEqual(self.master.get("robot").sensor_errors, {"x": "unavailable"})

    def test_closed_master_rejects_commands(self):
        self.hello()
        node = self.master.get("robot")
        self.master.close()
        self.master.close()
        with self.assertRaises(RuntimeError):
            node.servo("servo", 90)

    def test_decoder_limits_datagram_size(self):
        with self.assertRaises(ValueError):
            decode_packet(b' ' * 4097)
