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
        try:
            self.sock.sendto(json.dumps(pkt, separators=(",", ":")).encode("utf-8"), addr)
        except OSError:
            pass

    def _rx_loop(self) -> None:
        while self.running:
            try:
                data, addr = self.sock.recvfrom(2048)
                msg = json.loads(data.decode("utf-8"))
            except socket.timeout:
                continue
            except Exception:
                continue

            self._master_addr = addr
            cmd = msg.get("cmd")
            if cmd == "PING":
                self._send_state(addr)
            elif cmd == "ACT":
                act_name = msg.get("name", "servo")
                angle = int(msg.get("angle", msg.get("value", msg.get("v1", 90))))
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
