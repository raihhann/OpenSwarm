import json
import socket
import unittest

from unittest.mock import patch

from openswarm import SwarmMaster
from openswarm_slave import SwarmNode
from openswarm_slave.hal_linux import LinuxHAL
from openswarm_slave.protocol import decode_command, schedule_delay_ms


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

    def test_out_of_order_rejection_and_state_ack(self):
        node = self.node()
        calls = []
        node.register_custom_actuator("servo", lambda v1, v2, data: calls.append(v1))

        # Send ACT with seq=10 -> executed
        node._sock = FakeSocket(json.dumps({"cmd": "ACT", "name": "servo", "angle": 45, "seq": 10}).encode())
        node._handle_incoming()
        self.assertEqual(calls, [45])
        self.assertEqual(node._last_cmd_seq, 10)
        self.assertEqual(node._dropped_out_of_order, 0)

        # Send stale ACT with seq=9 and duplicate seq=10 -> both rejected
        for stale_seq in (9, 10):
            node._sock = FakeSocket(json.dumps({"cmd": "ACT", "name": "servo", "angle": 90, "seq": stale_seq}).encode())
            node._handle_incoming()
        self.assertEqual(calls, [45])
        self.assertEqual(node._last_cmd_seq, 10)
        self.assertEqual(node._dropped_out_of_order, 2)

        # Send newer ACT with seq=11 -> executed
        node._sock = FakeSocket(json.dumps({"cmd": "ACT", "name": "servo", "angle": 120, "seq": 11}).encode())
        node._handle_incoming()
        self.assertEqual(calls, [45, 120])
        self.assertEqual(node._last_cmd_seq, 11)

        # Telemetry includes ack=11
        node._send_telemetry()
        self.assertEqual(node._sock.sent[-1]["ack"], 11)

        # A delayed PING responds without rewinding the current session.
        node._sock = FakeSocket(json.dumps({"cmd": "PING", "seq": 1}).encode())
        node._handle_incoming()
        self.assertEqual(node._last_cmd_seq, 11)
        self.assertEqual(node._sock.sent[-1]["ack"], 11)

    def test_scheduled_actuation_and_stop_clearing(self):
        # Modular wraparound math check
        self.assertEqual(schedule_delay_ms(20, 32758), 30)
        self.assertEqual(schedule_delay_ms(32758, 20), -30)

        node = self.node()
        node._start_time = 100.0
        calls = []
        node.register_custom_actuator("servo", lambda v1, v2, data: calls.append(v1))

        # 1. Future at_ms (+50 ms from uptime_ms=1000) queues without immediate execution
        with patch("openswarm_slave.node.time.monotonic", return_value=101.000):
            node._sock = FakeSocket(json.dumps({"cmd": "ACT", "name": "servo", "angle": 75, "at_ms": 1050}).encode())
            node._handle_incoming()
        self.assertEqual(calls, [])
        self.assertIn("servo", node._pending_actuations)

        # Before due time (101.030 -> uptime 1030 ms), nothing fires
        node._run_due_actuations(101.030)
        self.assertEqual(calls, [])

        # At due time (101.050 -> uptime 1050 ms), pending command fires
        node._run_due_actuations(101.050)
        self.assertEqual(calls, [75])
        self.assertEqual(node._pending_actuations, {})

        # 2. Past/due at_ms (delta_ms <= 0) executes immediately
        with patch("openswarm_slave.node.time.monotonic", return_value=102.000):
            node._sock = FakeSocket(json.dumps({"cmd": "ACT", "name": "servo", "angle": 90, "at_ms": 1990}).encode())
            node._handle_incoming()
        self.assertEqual(calls, [75, 90])

        # 3. STOP clears queued pending actuations before they can fire and notifies CUSTOM with STOP
        with patch("openswarm_slave.node.time.monotonic", return_value=103.000):
            node._sock = FakeSocket(json.dumps({"cmd": "ACT", "name": "servo", "angle": 135, "at_ms": 3100}).encode())
            node._handle_incoming()
            self.assertIn("servo", node._pending_actuations)
            node._sock = FakeSocket(json.dumps({"cmd": "STOP"}).encode())
            node._handle_incoming()
        self.assertEqual(node._pending_actuations, {})
        node._run_due_actuations(104.000)
        self.assertEqual(calls, [75, 90, 0])

    def test_command_lease_expires_despite_ping_and_renews_on_act(self):
        node = self.node()
        node._start_time = 200.0
        history = []
        node.register_custom_actuator("drive", lambda v1, v2, data: history.append((v1, v2)))

        # 1. Start leased drive (lease_ms=200 -> expires at 201.200)
        with patch("openswarm_slave.node.time.monotonic", return_value=201.000):
            node._sock = FakeSocket(
                json.dumps({"cmd": "ACT", "name": "drive", "left": 180, "right": 180, "lease_ms": 200}).encode()
            )
            node._handle_incoming()
        self.assertEqual(history, [(180, 180)])
        self.assertIn("drive", node._active_leases)

        # 2. Send PING at 201.100 and 201.180 -> resets transport watchdog, but does NOT extend lease
        for ping_t in (201.100, 201.180):
            with patch("openswarm_slave.node.time.monotonic", return_value=ping_t):
                node._sock = FakeSocket(json.dumps({"cmd": "PING"}).encode())
                node._handle_incoming()
                node._run_due_actuations(ping_t)
        self.assertEqual(history, [(180, 180)])

        # 3. At 201.205, lease expires despite recent PINGs -> actuator stops (0, 0)
        node._run_due_actuations(201.205)
        self.assertEqual(history[-1], (0, 0))
        self.assertEqual(node._lease_expirations, 1)

        # 4. Renewing with a fresh ACT before expiration extends the lease
        with patch("openswarm_slave.node.time.monotonic", return_value=202.000):
            node._sock = FakeSocket(
                json.dumps({"cmd": "ACT", "name": "drive", "left": 100, "right": 100, "lease_ms": 200}).encode()
            )
            node._handle_incoming()
        with patch("openswarm_slave.node.time.monotonic", return_value=202.150):
            node._sock = FakeSocket(
                json.dumps({"cmd": "ACT", "name": "drive", "left": 120, "right": 120, "lease_ms": 200}).encode()
            )
            node._handle_incoming()
        # At 202.250 (past original 202.200 deadline, before renewed 202.350 deadline), still running
        node._run_due_actuations(202.250)
        self.assertEqual(history[-1], (120, 120))
        self.assertEqual(node._lease_expirations, 1)

        # 5. Combining at_ms + lease_ms starts lease countdown when the scheduled actuation fires
        with patch("openswarm_slave.node.time.monotonic", return_value=203.000):
            # uptime = 3000 ms, schedule at 3050 ms (+50 ms) with 100 ms lease -> fires at 203.050, expires at 203.150
            node._sock = FakeSocket(
                json.dumps({"cmd": "ACT", "name": "drive", "left": 200, "right": 200, "at_ms": 3050, "lease_ms": 100}).encode()
            )
            node._handle_incoming()
        node._run_due_actuations(203.050)
        self.assertEqual(history[-1], (200, 200))
        node._run_due_actuations(203.120)
        self.assertEqual(history[-1], (200, 200))
        node._run_due_actuations(203.155)
        self.assertEqual(history[-1], (0, 0))
        self.assertEqual(node._lease_expirations, 2)

    def test_complete_emergency_stop_coverage_and_safety_diagnostics(self):
        node = self.node()
        node._start_time = 300.0
        custom_calls = []
        node.register_pwm_output("heater", 12)
        node.register_servo("gripper", 18)
        node.register_custom_actuator("custom_drv", lambda v1, v2, data: custom_calls.append((v1, v2, data)))

        # Activate PWM_OUT, SERVO, and CUSTOM
        with patch("openswarm_slave.node.time.monotonic", return_value=301.000):
            for pkt in (
                {"cmd": "ACT", "name": "heater", "value": 200, "seq": 5},
                {"cmd": "ACT", "name": "gripper", "angle": 110, "seq": 6},
                {"cmd": "ACT", "name": "custom_drv", "v1": 42, "v2": 7, "data": "RUN", "seq": 7, "lease_ms": 100},
                # Out-of-order seq=6 -> increments seq_drop
                {"cmd": "ACT", "name": "heater", "value": 255, "seq": 6},
            ):
                node._sock = FakeSocket(json.dumps(pkt).encode())
                node._handle_incoming()

        self.assertEqual(node.hal._sim_pins[12], 200)
        self.assertTrue(node._actuators["gripper"]["holding"])
        self.assertEqual(custom_calls, [(42, 7, "RUN")])
        self.assertEqual(node._dropped_out_of_order, 1)

        # Lease expiration on custom_drv calls (0, 0, "STOP") and increments lease_exp
        node._run_due_actuations(301.150)
        self.assertEqual(custom_calls[-1], (0, 0, "STOP"))
        self.assertEqual(node._lease_expirations, 1)

        # STOP zeroes PWM_OUT, releases SERVO holding, and invokes CUSTOM with (0, 0, "STOP")
        with patch("openswarm_slave.node.time.monotonic", return_value=301.200):
            node._sock = FakeSocket(json.dumps({"cmd": "STOP", "seq": 8}).encode())
            node._handle_incoming()
        self.assertEqual(node.hal._sim_pins[12], 0)
        self.assertFalse(node._actuators["gripper"]["holding"])
        self.assertEqual(custom_calls[-1], (0, 0, "STOP"))

        # Simulate watchdog trip -> increments _watchdog_trips and emits wd_trips, lease_exp, seq_drop in STATE
        node._watchdog_trips += 1
        node._sock = FakeSocket(b"{}")
        node._send_telemetry()
        state = node._sock.sent[-1]
        self.assertEqual(state["wd_trips"], 1)
        self.assertEqual(state["lease_exp"], 1)
        self.assertEqual(state["seq_drop"], 1)
