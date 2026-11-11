"""Verify the hardware-test harness on local UDP, without claiming physical results."""
import contextlib
import io
import unittest
import json
import socket
from unittest.mock import MagicMock, patch

from benchmarks.hardware.linux_probe import create_probe
from benchmarks.hardware.validate_node import run, Session, ObservationError
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
        original_send = Session.send
        dropped = []
        def drop_first_cancel_target(session, packet):
            if (session.phase == "scheduled_preservation_and_stop_cancellation" and
                    packet.get("cmd") == "ACT" and packet.get("seq") == 11 and not dropped):
                dropped.append(packet)
                return
            original_send(session, packet)
        with contextlib.redirect_stdout(io.StringIO()):
            node = self.start_probe("probe_rpi")
            with patch.object(Session, "send", drop_first_cancel_target):
                result = run("127.0.0.1", node.udp_port)
        self.assertEqual(len(result["cases"]), 7)
        self.assertTrue(all(c["status"] == "PASS" for c in result["cases"]), result["cases"])
        self.assertTrue(any(item["direction"] == "rx" for item in result["packet_log"]))
        scheduled = next(c for c in result["cases"] if c["name"].startswith("scheduled_"))
        self.assertEqual(scheduled["detail"]["delivery_retries"], 1)
        endpoints = {tuple(p["local_endpoint"]) for p in result["packet_log"]}
        self.assertEqual(len(endpoints), 1)

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
        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(result["causal_interval_violations"], 0)

    def test_unexplained_ack_reset_is_classified_not_silently_passed(self):
        fake = MagicMock()
        fake.getsockname.return_value = ("127.0.0.1", 12345)
        incoming = dict(type="STATE", uptime_ms=101, wd_trips=3, sensors={"value": 0})
        fake.recvfrom.return_value = (json.dumps(incoming).encode(), ("127.0.0.1", 4210))
        with patch("benchmarks.hardware.validate_node.socket.socket", return_value=fake):
            session = Session("127.0.0.1", 4210, [])
        session.allow_reset = False
        session.armed = True
        session.last_state = dict(uptime_ms=100, ack=11, wd_trips=3)
        with self.assertRaises(ObservationError) as error:
            session.receive()
        self.assertEqual(error.exception.kind, "unexpected_session_reset")

    def test_wait_sends_keepalive_while_observation_is_delayed(self):
        fake = MagicMock()
        fake.getsockname.return_value = ("127.0.0.1", 12345)
        clock = [0.0]
        def delayed_packet(count):
            clock[0] += 0.05
            if clock[0] < 0.7:
                raise socket.timeout()
            return json.dumps(dict(type="STATE", uptime_ms=700, ack=11, sensors={})).encode(), ("127.0.0.1", 4210)
        fake.recvfrom.side_effect = delayed_packet
        with patch("benchmarks.hardware.validate_node.socket.socket", return_value=fake):
            session = Session("127.0.0.1", 4210, [])
        session.keepalive = True
        with patch("benchmarks.hardware.validate_node.time.monotonic", side_effect=lambda: clock[0]):
            packet = session.wait(lambda p: p.get("ack") == 11)
        self.assertEqual(packet["ack"], 11)
        self.assertGreaterEqual(sum(p["direction"] == "tx" for p in session.log), 5)
