"""Verify the hardware-test harness on local UDP, without claiming physical results."""
import contextlib
import io
import unittest

from benchmarks.hardware.linux_probe import create_probe
from benchmarks.hardware.validate_node import run
from benchmarks.hardware.sync_trial import trial


class HardwareHarnessTests(unittest.TestCase):
    def start_probe(self, name):
        node = create_probe(simulation=True, node_id=name, port=0)
        node._send_hello = lambda: None
        node.hal.local_ip = lambda: "127.0.0.1"
        node.start(block=False)
        self.addCleanup(node.stop)
        return node

    def test_live_udp_fault_and_deadlock_runner(self):
        with contextlib.redirect_stdout(io.StringIO()):
            node = self.start_probe("probe_rpi")
            result = run("127.0.0.1", node.udp_port)
        self.assertEqual(len(result["cases"]), 6)
        self.assertTrue(all(c["status"] == "PASS" for c in result["cases"]), result["cases"])
        self.assertTrue(any(item["direction"] == "rx" for item in result["packet_log"]))

    def test_sdk_trial_records_every_pose_and_declares_estimate(self):
        with contextlib.redirect_stdout(io.StringIO()):
            nodes = [self.start_probe("probe_a"), self.start_probe("probe_b")]
            raw = []
            result = trial([(n.node_id, "127.0.0.1:" + str(n.udp_port)) for n in nodes],
                           poses=2, record_callback=raw.append)
        self.assertEqual(len(raw), 4)
        for mode in ("immediate", "scheduled"):
            self.assertEqual(result["estimated_skew_ms"][mode]["count"], 2)
        self.assertIn("No independent timing reference", result["limitations"])
