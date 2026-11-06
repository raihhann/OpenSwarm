"""
Virtual Slave Node Emulator for OpenSwarm.
Simulates an ESP32 or RP2040 slave running the SwarmNode library.
- Connects to Wi-Fi / Localhost UDP (Port 4210 for commands, broadcasts HELLO on 4211).
- Prints real-time formatted [CMD] execution and [TELEMETRY] outputs to terminal,
  perfect for split-screen recordings.
- Responds to Master watchdog heartbeats and motor/sensor commands with simulated physics.
"""

import argparse
import json
import math
import socket
import threading
import time

SWARM_DEFAULT_PORT = 4210
SWARM_DISCOVERY_PORT = 4211
SWARM_WATCHDOG_SEC = 0.5
SWARM_TELEMETRY_SEC = 0.05


class VirtualSlaveNode:
    def __init__(self, node_id: str, board_type: str = "ESP32", port: int = SWARM_DEFAULT_PORT):
        self.node_id = node_id
        self.board_type = board_type
        self.port = port
        self.running = True
        
        # Simulated Hardware State
        self.motors = {"left": 0.0, "right": 0.0}
        self.sensors = {
            "battery_V": 11.8,
            "rssi_dbm": -48,
            "encoder_L": 0,
            "encoder_R": 0
        }
        self._start_time = time.monotonic()
        self.last_cmd_time = self._start_time
        self.master_addr = None
        self._lock = threading.Lock()

        # UDP Sockets
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", self.port))
        self.sock.settimeout(0.05)

        # Broadcast Socket
        self.bcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.bcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def start(self):
        print("=" * 65)
        print(f" [OpenSwarm Virtual Slave] Target: {self.board_type} | Node ID: '{self.node_id}'")
        print(f" Network: Online (127.0.0.1:{self.port}) | Watchdog: 500ms Active")
        print(f" Core Rule: void loop() is 100% EMPTY. Remote HAL listening...")
        print("=" * 65)

        # Background Threads for Discovery Broadcast, Telemetry, and Physics
        threading.Thread(target=self._discovery_loop, daemon=True).start()
        threading.Thread(target=self._telemetry_loop, daemon=True).start()
        threading.Thread(target=self._physics_loop, daemon=True).start()

        self._rx_loop()

    def close(self):
        self.running = False
        self.sock.close()
        self.bcast_sock.close()

    def _discovery_loop(self):
        """Broadcasts 1 Hz HELLO beacon until discovered."""
        while self.running:
            hello = {
                "type": "HELLO",
                "node": self.node_id,
                "board": self.board_type,
                "port": self.port,
                "actuators": ["drive"],
                "sensors": ["battery_V", "rssi_dbm"]
            }
            try:
                msg = json.dumps(hello).encode("utf-8")
                self.bcast_sock.sendto(msg, ("255.255.255.255", SWARM_DISCOVERY_PORT))
                self.bcast_sock.sendto(msg, ("127.0.0.1", SWARM_DISCOVERY_PORT))
            except OSError:
                if self.running:
                    raise
            time.sleep(1.0)

    def _telemetry_loop(self):
        """Streams 20 Hz telemetry back to master when connected."""
        while self.running:
            with self._lock:
                master_addr = self.master_addr
                sensors = dict(self.sensors)
            if master_addr:
                state = {
                    "type": "STATE",
                    "node": self.node_id,
                    "uptime_ms": int((time.monotonic() - self._start_time) * 1000),
                    "sensors": sensors,
                }
                try:
                    self.sock.sendto(json.dumps(state).encode("utf-8"), master_addr)
                except OSError:
                    if self.running:
                        raise
            time.sleep(SWARM_TELEMETRY_SEC)

    def _physics_loop(self):
        """Updates simulated encoders and battery based on motor activity."""
        while self.running:
            now = time.monotonic()
            # Safety watchdog: Auto-stop motors if Master is silent > 500ms
            with self._lock:
                if (now - self.last_cmd_time) > SWARM_WATCHDOG_SEC:
                    if self.motors["left"] != 0 or self.motors["right"] != 0:
                        self.motors["left"] = 0.0
                        self.motors["right"] = 0.0
                        print(f"[{time.strftime('%H:%M:%S')}] \033[93m[WATCHDOG]\033[0m Master silent > 500ms -> Motors Emergency STOP")

                # Update simulated encoders
                self.sensors["encoder_L"] += int(self.motors["left"] * 0.2)
                self.sensors["encoder_R"] += int(self.motors["right"] * 0.2)
            time.sleep(0.05)

    def _rx_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(2048)
                packet = json.loads(data.decode("utf-8"))
                if not isinstance(packet, dict):
                    continue
                cmd = packet.get("cmd")
                with self._lock:
                    self.master_addr = addr
                    self.last_cmd_time = time.monotonic()

                if cmd == "PING":
                    self._send_state(addr)
                elif cmd == "ACT" and packet.get("name") == "drive":
                    left = self._motor_value(packet.get("left", 0))
                    right = self._motor_value(packet.get("right", 0))
                    with self._lock:
                        self.motors["left"] = left
                        self.motors["right"] = right
                    # Pretty ANSI Terminal Output
                    status = "\033[92mFORWARD\033[0m" if (left > 0 and right > 0) else (
                        "\033[96mROTATE\033[0m" if (left * right < 0) else (
                            "\033[91mSTOP\033[0m" if (left == 0 and right == 0) else "\033[93mREVERSE\033[0m"
                        )
                    )
                    ts = time.strftime('%H:%M:%S')
                    print(f"[{ts}] \033[1m[CMD]\033[0m DRIVE -> L={left:+04d} | R={right:+04d} [{status}] | Enc: ({self.sensors['encoder_L']}, {self.sensors['encoder_R']})")
                elif cmd == "STOP":
                    with self._lock:
                        self.motors = {"left": 0, "right": 0}
                    print(f"[{time.strftime('%H:%M:%S')}] \033[91m[CMD STOP]\033[0m All Actuators Disabled")

            except socket.timeout:
                continue
            except json.JSONDecodeError:
                continue
            except OSError:
                if self.running:
                    raise
                return

    @staticmethod
    def _motor_value(value):
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return max(-255, min(255, value))
        if not isinstance(value, float) or not math.isfinite(value):
            return 0
        return max(-255, min(255, int(value)))

    def _send_state(self, addr):
        with self._lock:
            sensors = dict(self.sensors)
        state = {
            "type": "STATE",
            "node": self.node_id,
            "uptime_ms": int((time.monotonic() - self._start_time) * 1000),
            "sensors": sensors,
        }
        self.sock.sendto(json.dumps(state).encode("utf-8"), addr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenSwarm Virtual Slave Node")
    parser.add_argument("--id", type=str, default="tug_esp32", help="Unique Node ID")
    parser.add_argument("--board", type=str, default="ESP32", choices=["ESP32", "RP2040", "UNO_Q"], help="Board architecture")
    parser.add_argument("--port", type=int, default=4210, help="UDP listening port")
    args = parser.parse_args()

    node = VirtualSlaveNode(node_id=args.id, board_type=args.board, port=args.port)
    try:
        node.start()
    except KeyboardInterrupt:
        print("\n[SwarmNode] Shutting down node cleanly.")
    finally:
        node.close()
