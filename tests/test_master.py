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

    def test_seq_ack_rtt_jitter_and_clock_offset(self):
        sent = []
        node = RemoteSwarmNode("robot", "127.0.0.1", 4210, lambda ip, port, payload: sent.append(payload))
        with patch("openswarm.node.time.monotonic", return_value=10.000):
            node.ping()
        self.assertEqual(sent[-1], {"cmd": "PING", "seq": 1})

        with patch("openswarm.node.time.monotonic", return_value=10.020):
            node._update_state(5000, {"x": 1}, ack=1)
        self.assertEqual(node.last_ack_seq, 1)
        self.assertAlmostEqual(node.rtt_ms, 20.0, places=3)
        self.assertAlmostEqual(node.jitter_ms, 0.0, places=3)
        # master_rx_ms = 10020.0, rtt/2 = 10.0 -> master_mid = 10010.0 -> offset = 5000 - 10010 = -5010.0
        self.assertAlmostEqual(node.clock_offset_ms, -5010.0, places=3)

        with patch("openswarm.node.time.monotonic", return_value=11.000):
            node.servo("arm", 90)
        self.assertEqual(sent[-1]["seq"], 2)

        with patch("openswarm.node.time.monotonic", return_value=11.036):
            node._update_state(6028, {"x": 2}, ack=2)
        self.assertEqual(node.last_ack_seq, 2)
        self.assertAlmostEqual(node.rtt_ms, 36.0, places=3)
        self.assertAlmostEqual(node.jitter_ms, 1.0, places=3)  # |36 - 20| / 16 = 1.0

    def test_master_parses_ack_and_rejects_invalid_ack(self):
        self.hello()
        node = self.master.get("robot")
        with patch.object(self.master, "_send_json"):
            node.ping()
        seq = node._tx_seq
        self.master._handle_packet(
            json.dumps({"type": "STATE", "node": "robot", "uptime_ms": 1200, "ack": seq, "sensors": {"x": 5}}).encode(),
            ("127.0.0.1", 4210),
        )
        self.assertEqual(node.last_ack_seq, seq)
        self.assertIsNotNone(node.rtt_ms)
        self.assertIsNotNone(node.clock_offset_ms)

        # Invalid ack values must be ignored without mutating state
        for bad_ack in [0, -1, 40000, True, "1"]:
            self.master._handle_packet(
                json.dumps({"type": "STATE", "node": "robot", "uptime_ms": 1300, "ack": bad_ack, "sensors": {"x": 99}}).encode(),
                ("127.0.0.1", 4210),
            )
        self.assertEqual(node.read("x"), 5)

    def test_sync_actuate_aligns_heterogeneous_node_clocks(self):
        self.hello("base", port=4210)
        self.hello("elbow", port=4213)
        base = self.master.get("base")
        elbow = self.master.get("elbow")
        # Different boot times -> different clock offsets relative to Master monotonic clock
        base.clock_offset_ms = 5000.0
        elbow.clock_offset_ms = 40000.0  # wraps around 32768

        sent = []
        with patch.object(self.master, "_send_json", side_effect=lambda ip, port, payload: sent.append((port, payload))):
            with patch("openswarm.master.time.monotonic", return_value=2.000):
                count = self.master.sync_actuate(
                    [
                        ("base", "servo", 90),
                        {"node": elbow, "name": "servo", "angle": 120},
                    ],
                    lead_ms=40.0,
                )
        self.assertEqual(count, 2)
        # t_exec = 2.040s = 2040 ms
        # base: (2040 + 5000) & 0x7FFF = 7040
        # elbow: (2040 + 40000) & 0x7FFF = 42040 & 0x7FFF = 9272
        self.assertEqual(sent[0][1]["at_ms"], 7040)
        self.assertEqual(sent[1][1]["at_ms"], 9272)

    def test_node_and_sync_actuate_lease_ms(self):
        sent = []
        node = RemoteSwarmNode("robot", "127.0.0.1", 4210, lambda ip, port, payload: sent.append(payload))
        node.default_lease_ms = 300
        node.drive("drive", 150, 150)
        self.assertEqual(sent[-1]["lease_ms"], 300)

        node.drive("drive", 180, 180, lease_ms=120)
        self.assertEqual(sent[-1]["lease_ms"], 120)

        for invalid_lease in (0, -10, 30001, True):
            with self.assertRaises(ValueError):
                node.drive("drive", 100, 100, lease_ms=invalid_lease)

    def test_master_parses_safety_diagnostic_counters(self):
        self.hello()
        node = self.master.get("robot")
        self.assertEqual(node.watchdog_trips, 0)
        self.assertEqual(node.lease_expirations, 0)
        self.assertEqual(node.dropped_out_of_order, 0)

        self.master._handle_packet(
            json.dumps(
                {
                    "type": "STATE",
                    "node": "robot",
                    "uptime_ms": 2500,
                    "wd_trips": 2,
                    "lease_exp": 5,
                    "seq_drop": 3,
                    "sensors": {"x": 10},
                }
            ).encode(),
            ("127.0.0.1", 4210),
        )
        self.assertEqual(node.watchdog_trips, 2)
        self.assertEqual(node.lease_expirations, 5)
        self.assertEqual(node.dropped_out_of_order, 3)

        # Negative or non-integer diagnostic counters are rejected without mutating node state
        for bad_field in ({"wd_trips": -1}, {"lease_exp": True}, {"seq_drop": "bad"}):
            self.master._handle_packet(
                json.dumps(
                    {
                        "type": "STATE",
                        "node": "robot",
                        "uptime_ms": 2600,
                        **bad_field,
                        "sensors": {"x": 99},
                    }
                ).encode(),
                ("127.0.0.1", 4210),
            )
        self.assertEqual(node.read("x"), 10)
        self.assertEqual(node.watchdog_trips, 2)
        self.assertEqual(node.lease_expirations, 5)
        self.assertEqual(node.dropped_out_of_order, 3)
