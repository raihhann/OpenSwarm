"""Control/data reordering regressions through real slave command handlers."""
import contextlib
import io
import json
import unittest
from unittest.mock import MagicMock, patch

from openswarm.protocol import sequence_is_newer
from openswarm.virtual_slave import VirtualSlaveNode
from openswarm_slave.protocol import sequence_is_newer as linux_is_newer
from tests import test_linux_slave
from projects.hydra_arm.master.virtual_arm_slaves import VirtualServoSlave


class SequenceOrderingTests(unittest.TestCase):
    def implementations(self):
        node = test_linux_slave.SlaveTests().node()
        applied = []
        node.register_custom_actuator("drive", lambda a, b, data: applied.append(a))
        channel = test_linux_slave.FakeSocket(b"{}")
        node._sock = channel

        def linux_send(packet, address):
            channel.packet = json.dumps(packet).encode()
            channel.recvfrom = lambda count: (channel.packet, address)
            node._handle_incoming()

        yield node, linux_send, lambda: node._last_cmd_seq, lambda: node._dropped_out_of_order, channel.sent
        with patch("socket.socket", return_value=MagicMock()):
            fleet = VirtualSlaveNode("fleet")
            arm = VirtualServoSlave("arm", "RP2040", 0, ["drive"], {})
        for virtual in (fleet, arm):
            replies = []
            virtual._send_state = lambda address, v=virtual, r=replies: r.append({"ack": v.last_cmd_seq})
            yield (virtual, virtual._handle_packet, lambda v=virtual: v.last_cmd_seq,
                   lambda v=virtual: v.dropped_out_of_order, replies)

    def test_delayed_ping_and_stop_cannot_rewind_watermark(self):
        with contextlib.redirect_stdout(io.StringIO()):
            for node, send, ack, drops, replies in self.implementations():
                with self.subTest(implementation=type(node).__name__):
                    address = ("127.0.0.1", 40000)
                    act = lambda seq, **fields: send({"cmd": "ACT", "name": "drive", "left": 110,
                                                     "angle": 110, "seq": seq, **fields}, address)
                    act(10)
                    act(11)
                    for seq in (9, 11, 9):
                        send({"cmd": "PING", "seq": seq}, address)
                        self.assertEqual(replies[-1]["ack"], 11)
                    act(10)
                    send({"cmd": "PIN", "pin": 2, "value": 1, "seq": 10}, address)
                    self.assertEqual((ack(), drops()), (11, 2))
                    # STOP must still execute when stale, without opening replay.
                    if hasattr(node, "pending_actuations"):
                        node.pending_actuations = {"drive": {}}
                    send({"cmd": "STOP", "seq": 8}, address)
                    self.assertEqual(ack(), 11)
                    if hasattr(node, "pending_actuations"):
                        self.assertFalse(node.pending_actuations)
                    if isinstance(node, VirtualSlaveNode):
                        self.assertEqual(node.motors, {"left": 0.0, "right": 0.0})
                    if isinstance(node, VirtualServoSlave):
                        self.assertFalse(any(node.holding.values()))
                    act(10)
                    self.assertEqual((ack(), drops()), (11, 3))
                    act(12)
                    send({"cmd": "PING", "seq": 14}, address)
                    act(13)
                    self.assertEqual((ack(), drops()), (14, 4))

    def test_wraparound_and_real_session_boundaries(self):
        with contextlib.redirect_stdout(io.StringIO()):
            for node, send, ack, drops, replies in self.implementations():
                with self.subTest(implementation=type(node).__name__):
                    address = ("127.0.0.1", 40000)
                    def act(seq, addr=address):
                        send({"cmd": "ACT", "name": "drive", "left": 10, "angle": 10, "seq": seq}, addr)
                    act(32766)
                    send({"cmd": "PING", "seq": 32767}, address)
                    act(1)
                    send({"cmd": "PING", "seq": 32766}, address)
                    self.assertEqual(replies[-1]["ack"], 1)
                    act(32767)
                    act(2)
                    self.assertEqual((ack(), drops()), (2, 1))
                    act(1, ("127.0.0.1", 40001))
                    self.assertEqual(ack(), 1)
                    act(100)
                    node._watchdog_tripped = True
                    act(1)
                    self.assertEqual(ack(), 1)

    def test_sequence_contract_matches_across_python_packages(self):
        for previous in (0, 1, 100, 16383, 16384, 32766, 32767):
            for incoming in (False, None, -1, 0, 1, 2, 100, 16483, 16484, 32766, 32767, 32768):
                self.assertEqual(sequence_is_newer(incoming, previous), linux_is_newer(incoming, previous))
        self.assertTrue(sequence_is_newer(16483, 100))
        self.assertFalse(sequence_is_newer(16484, 100))
        self.assertFalse(sequence_is_newer(32767, 1))

    def test_delayed_controls_preserve_pending_command_but_stop_cancels_it(self):
        with patch("time.monotonic", return_value=100.0), contextlib.redirect_stdout(io.StringIO()):
            for node, send, ack, drops, replies in self.implementations():
                with self.subTest(implementation=type(node).__name__):
                    address = ("127.0.0.1", 40000)
                    send({"cmd": "ACT", "name": "drive", "left": 120, "angle": 120,
                          "seq": 12, "at_ms": 50, "lease_ms": 150}, address)
                    pending = getattr(node, "_pending_actuations", None)
                    if pending is None:
                        pending = node.pending_actuations
                    self.assertIn("drive", pending)
                    original = dict(pending["drive"])
                    send({"cmd": "PING", "seq": 9}, address)
                    send({"cmd": "ACT", "name": "drive", "left": 10, "angle": 10, "seq": 10}, address)
                    self.assertEqual(pending["drive"], original)
                    self.assertEqual((ack(), drops()), (12, 1))
                    send({"cmd": "STOP", "seq": 8}, address)
                    self.assertFalse(pending)
                    self.assertEqual(ack(), 12)
