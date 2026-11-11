#!/usr/bin/env python3
"""
===============================================================================
OpenSwarm HydraArm — Local 3-Controller Virtual Slave Emulator
===============================================================================
Spawns the 3 heterogeneous Slave nodes on localhost UDP so you can test
`hydra_arm_studio.py` or `hydra_arm_cli.py` even before powering on the
physical ESP32, RP2040, and Raspberry Pi:
  1. arm_base_esp32           (ESP32)        on UDP Port 4210 -> ["servo"] (Base)
  2. arm_elbow_rp2040         (RP2040)       on UDP Port 4213 -> ["servo"] (Elbow)
  3. arm_shoulder_gripper_rpi (Raspberry Pi) on UDP Port 4214 -> ["shoulder_servo", "gripper_servo", "servo"]
===============================================================================
"""

import json
import socket
import threading
import time
import sys
from pathlib import Path

MASTER_PACKAGE = Path(__file__).resolve().parents[3] / "master"
if str(MASTER_PACKAGE) not in sys.path:
    sys.path.insert(0, str(MASTER_PACKAGE))
from openswarm.protocol import sequence_is_newer
from typing import Dict, Any, List

SWARM_DISCOVERY_PORT = 4211


class VirtualServoSlave:
    def __init__(self, node_id: str, board: str, port: int, actuators: List[str], sensors: Dict[str, Any]):
        self.node_id = node_id
        self.board = board
        self.port = port
        self.actuators = list(actuators)
        self.sensors = dict(sensors)
        self.running = True
        self._start = time.monotonic()
        self._master_addr = None
        self._last_cmd_time = self._start
        self._watchdog_tripped = False
        self.watchdog_trips = 0
        self.last_cmd_seq = 0
        self.dropped_out_of_order = 0
        self.lease_expirations = 0
        self.pending_actuations: Dict[str, Dict[str, Any]] = {}
        self.active_leases: Dict[str, float] = {}
        self.holding: Dict[str, bool] = {a: False for a in self.actuators}

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", self.port))
        self.sock.settimeout(0.05)

        self.bcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if hasattr(socket, "SO_BROADCAST"):
            self.bcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def start_background(self) -> None:
        threading.Thread(target=self._hello_loop, daemon=True).start()
        threading.Thread(target=self._telemetry_loop, daemon=True).start()
        threading.Thread(target=self._rx_loop, daemon=True).start()

    def _hello_loop(self) -> None:
        while self.running:
            pkt = {
                "type": "HELLO",
                "virtual": True,
                "max_command_bytes": 2048,
                "node": self.node_id,
                "board": self.board,
                "ip": "127.0.0.1",
                "port": self.port,
                "actuators": self.actuators,
                "sensors": list(self.sensors.keys()),
            }
            raw = json.dumps(pkt, separators=(",", ":")).encode("utf-8")
            try:
                self.bcast_sock.sendto(raw, ("127.0.0.1", SWARM_DISCOVERY_PORT))
            except OSError:
                pass
            time.sleep(1.0)

    def _telemetry_loop(self) -> None:
        while self.running:
            if self._master_addr is not None:
                self._send_state(self._master_addr)
            time.sleep(0.05)

    def _send_state(self, addr) -> None:
        pkt = {
            "type": "STATE",
            "node": self.node_id,
            "uptime_ms": int((time.monotonic() - self._start) * 1000),
            "sensors": self.sensors,
        }
        if self.last_cmd_seq > 0:
            pkt["ack"] = self.last_cmd_seq
        if self.watchdog_trips > 0:
            pkt["wd_trips"] = self.watchdog_trips
        if self.lease_expirations > 0:
            pkt["lease_exp"] = self.lease_expirations
        if self.dropped_out_of_order > 0:
            pkt["seq_drop"] = self.dropped_out_of_order
        try:
            self.sock.sendto(json.dumps(pkt, separators=(",", ":")).encode("utf-8"), addr)
        except OSError:
            pass

    def _rx_loop(self) -> None:
        while self.running:
            now = time.monotonic()
            if self._master_addr is not None and (now - self._last_cmd_time) > 0.5:
                if not self._watchdog_tripped:
                    self._watchdog_tripped = True
                    self.watchdog_trips += 1
                    self.last_cmd_seq = 0
                    self.pending_actuations.clear()
                    self.active_leases.clear()
                    for k in self.holding:
                        self.holding[k] = False
            due = [k for k, v in self.pending_actuations.items() if now >= v["due_mono"]]
            for k in due:
                item = self.pending_actuations.pop(k, None)
                if item:
                    lease_ms = item.get("lease_ms")
                    if lease_ms is not None:
                        self.active_leases[k] = item["due_mono"] + (lease_ms / 1000.0)
                    else:
                        self.active_leases.pop(k, None)
                    self.holding[k] = True
                    ts = time.strftime("%H:%M:%S")
                    print(f"[{ts}] [{self.node_id:<18} | {self.board:<13}] {k:<15} -> {item['angle']:3d}° (scheduled)")
            expired = [k for k, due_mono in self.active_leases.items() if now >= due_mono]
            for k in expired:
                self.active_leases.pop(k, None)
                self.holding[k] = False
                self.lease_expirations += 1
            try:
                data, addr = self.sock.recvfrom(2048)
                msg = json.loads(data.decode("utf-8"))
            except socket.timeout:
                continue
            except Exception:
                continue

            self._handle_packet(msg, addr)

    def _handle_packet(self, msg, addr):
        """Process a command independently of the UDP receive loop."""
        if not isinstance(msg, dict):
            return
        if self._master_addr != addr or self._watchdog_tripped:
            self.last_cmd_seq = 0
        self._master_addr = addr
        self._last_cmd_time = time.monotonic()
        self._watchdog_tripped = False
        cmd = msg.get("cmd")
        raw_seq = msg.get("seq")
        seq = raw_seq if (not isinstance(raw_seq, bool) and isinstance(raw_seq, int) and 1 <= raw_seq <= 32767) else None
        if seq is not None:
            if sequence_is_newer(seq, self.last_cmd_seq):
                self.last_cmd_seq = seq
            elif cmd in ("ACT", "PIN"):
                self.dropped_out_of_order += 1
                return

        if cmd == "PING":
            self._send_state(addr)
        elif cmd == "STOP":
            self.pending_actuations.clear()
            self.active_leases.clear()
            for k in self.holding:
                self.holding[k] = False
        elif cmd == "ACT":
            act_name = msg.get("name", "servo")
            angle = int(msg.get("angle", msg.get("value", msg.get("v1", 90))))
            raw_at = msg.get("at_ms")
            at_ms = raw_at if (not isinstance(raw_at, bool) and isinstance(raw_at, int) and 0 <= raw_at <= 32767) else None
            raw_lease = msg.get("lease_ms")
            lease_ms = raw_lease if (not isinstance(raw_lease, bool) and isinstance(raw_lease, int) and 1 <= raw_lease <= 30000) else None
            now = time.monotonic()
            uptime_ms = int((now - self._start) * 1000)
            delta_ms = (((at_ms - (uptime_ms & 0x7FFF) + 16384) & 0x7FFF) - 16384) if at_ms is not None else 0
            if at_ms is not None and 1 <= delta_ms <= 1000:
                self.pending_actuations[act_name] = {
                    "due_mono": now + (delta_ms / 1000.0),
                    "angle": angle,
                    "lease_ms": lease_ms,
                }
                return
            self.pending_actuations.pop(act_name, None)
            if lease_ms is not None:
                self.active_leases[act_name] = now + (lease_ms / 1000.0)
            else:
                self.active_leases.pop(act_name, None)
            self.holding[act_name] = True
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] [{self.node_id:<18} | {self.board:<13}] {act_name:<15} -> {angle:3d}°")



def main() -> None:
    nodes = [
        VirtualServoSlave("arm_base_esp32",           "ESP32",        4210, ["servo"], {"rssi": -46.0}),
        VirtualServoSlave("arm_elbow_rp2040",         "RP2040",       4213, ["servo"], {"rssi": -51.0, "imu": [0.01, 0.02, 0.99, 0.0, 0.0, 0.0]}),
        VirtualServoSlave("arm_shoulder_gripper_rpi", "RASPBERRY_PI", 4214, ["shoulder_servo", "gripper_servo", "servo"], {"cpu_temp": 44.5, "rssi": -43.0}),
    ]
    print("=" * 74)
    print("  OpenSwarm HydraArm — Virtual Arm Slaves Online (127.0.0.1)")
    print("=" * 74)
    for n in nodes:
        n.start_background()
        print(f"  [ONLINE] {n.node_id:<18} ({n.board:<13}) -> 127.0.0.1:{n.port} | {n.actuators}")
    print("=" * 74)
    print("Keep this terminal open and run `python master/hydra_arm_studio.py`!\n")

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping virtual arm slaves.")


if __name__ == "__main__":
    main()
