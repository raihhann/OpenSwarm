"""Delayed ACKs, UDP reordering and concurrency must not corrupt clock mapping."""
import threading
import time
import unittest
from unittest.mock import patch

from openswarm import RemoteSwarmNode


class ClockEstimationTests(unittest.TestCase):
    def setUp(self):
        self.node = RemoteSwarmNode("probe", "127.0.0.1", 4210, lambda *args: None)

    def calibrate(self):
        with patch("openswarm.node.time.monotonic", return_value=10):
            self.node.ping()
        with patch("openswarm.node.time.monotonic", return_value=10.02):
            self.node._update_state(5000, {"value": 1}, ack=1)

    def test_act_ack_and_slow_ping_do_not_replace_low_delay_sample(self):
        self.calibrate()
        initial = self.node.clock_offset_ms
        with patch("openswarm.node.time.monotonic", return_value=11):
            self.node.servo("arm", 90)
        with patch("openswarm.node.time.monotonic", return_value=11.4):
            self.node._update_state(6390, {}, ack=2)
        self.assertEqual(self.node.clock_offset_ms, initial)
        with patch("openswarm.node.time.monotonic", return_value=12):
            self.node.ping()
        with patch("openswarm.node.time.monotonic", return_value=12.2):
            self.node._update_state(6993, {}, ack=3)
            snapshot = self.node.snapshot()
        self.assertEqual(self.node.clock_offset_ms, initial)
        self.assertLessEqual(snapshot["clock"]["lower_ms"], -5010)
        self.assertGreaterEqual(snapshot["clock"]["upper_ms"], -5010)

    def test_reordered_state_cannot_rewind_sensors_ack_or_clock(self):
        self.calibrate()
        initial = self.node.clock_offset_ms
        with patch("openswarm.node.time.monotonic", return_value=10.1):
            accepted = self.node._update_state(4900, {"value": 99}, ack=1)
        self.assertFalse(accepted)
        self.assertEqual(self.node.sensors, {"value": 1})
        self.assertEqual(self.node.clock_offset_ms, initial)
        self.assertEqual(self.node.last_ack_seq, 1)
        self.assertEqual(self.node.reordered_states, 1)

    def test_stale_calibration_expires_and_fresh_reboot_probe_resets_epoch(self):
        self.calibrate()
        with patch("openswarm.node.time.monotonic", return_value=16):
            self.assertIsNone(self.node.slave_time_ms())
            self.assertFalse(self.node.snapshot()["clock"]["fresh"])
            self.node.ping()
        with patch("openswarm.node.time.monotonic", return_value=16.01):
            self.assertTrue(self.node._update_state(100, {"value": 0}, ack=2))
            self.assertTrue(self.node.snapshot()["clock"]["fresh"])
        self.assertEqual(self.node.clock_resets, 1)
        self.assertEqual(len(self.node._clock_samples), 1)

    def test_endpoint_change_invalidates_calibration(self):
        self.calibrate()
        self.node._update_hello("127.0.0.2", 4210, "board", [], [])
        self.assertIsNone(self.node.clock_offset_ms)

    def test_recent_sample_takes_over_when_old_minimum_expires_between_pings(self):
        self.node._clock_samples = [(10, 100, 102), (14.9, 99, 105)]
        self.node._clock_sample = self.node._clock_samples[0]
        self.node.clock_offset_ms = 101
        with patch("openswarm.node.time.monotonic", return_value=15.05):
            self.assertIsNotNone(self.node.slave_time_ms())
            self.assertEqual(self.node.snapshot()["clock"]["sample_mono_s"], 14.9)

    def test_send_order_matches_sequence_order_with_concurrent_heartbeat(self):
        entered = threading.Event()
        sent = []
        def send(ip, port, packet):
            if packet["seq"] == 1:
                entered.set()
                time.sleep(0.02)
            sent.append(packet["seq"])
        self.node._send_fn = send
        first = threading.Thread(target=self.node.ping)
        second = threading.Thread(target=lambda: self.node.servo("arm", 90))
        first.start()
        self.assertTrue(entered.wait(1))
        second.start()
        first.join(1)
        second.join(1)
        self.assertEqual(sent, [1, 2])
