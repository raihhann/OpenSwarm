"""
SwarmMaster — Central Linux/Cross-Platform Master Engine for OpenSwarm.
- Listens on UDP Port 4211 for Slave auto-discovery broadcasts ("HELLO").
- Sends low-latency actuator commands and 5 Hz watchdog heartbeats ("PING") over UDP Port 4210.
- Receives 20 Hz sensor telemetry streams ("STATE") from all connected Slaves in a background thread.
"""

import json
import socket
import threading
import time
from typing import Any, Dict, Optional

from .node import RemoteSwarmNode

SWARM_DEFAULT_SLAVE_PORT = 4210
SWARM_DISCOVERY_PORT = 4211
SWARM_HEARTBEAT_SEC = 0.20  # 200ms keepalive (well below the 500ms Slave hardware watchdog)


class SwarmMaster:
    def __init__(self, discovery_port: int = SWARM_DISCOVERY_PORT, heartbeat_sec: float = SWARM_HEARTBEAT_SEC):
        self.discovery_port = discovery_port
        self.heartbeat_sec = heartbeat_sec
        self._nodes: Dict[str, RemoteSwarmNode] = {}
        self._lock = threading.Lock()
        self._running = True

        # 1. Command & Telemetry Socket (ephemeral port; Slaves reply with STATE to this socket)
        self._cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._cmd_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._cmd_sock.bind(("0.0.0.0", 0))
        self._cmd_sock.settimeout(0.05)

        # 2. Discovery Socket (listens on UDP 4211 for Slave HELLO broadcasts)
        self._disc_sock: Optional[socket.socket] = None
        try:
            self._disc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._disc_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_BROADCAST"):
                self._disc_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._disc_sock.bind(("0.0.0.0", self.discovery_port))
            self._disc_sock.settimeout(0.05)
        except OSError:
            # If another process is already bound to 4211, direct IP connect still works
            self._disc_sock = None

        # Start background network & heartbeat daemon threads
        self._rx_thread = threading.Thread(target=self._network_loop, daemon=True, name="OpenSwarmRx")
        self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="OpenSwarmHeartbeat")
        self._rx_thread.start()
        self._hb_thread.start()

    # -------------------------------------------------------------------------
    # Public Discovery & Connection API
    # -------------------------------------------------------------------------
    def connect(
        self,
        node_id: str,
        ip: Optional[str] = None,
        port: int = SWARM_DEFAULT_SLAVE_PORT,
        timeout: float = 10.0,
    ) -> RemoteSwarmNode:
        """
        Connects to a Slave node by its Node ID (e.g. 'esp32_node').
        - If `ip` is provided (e.g. ip='192.168.0.118'), connects immediately and verifies telemetry.
        - Otherwise, waits up to `timeout` seconds for the Slave's UDP auto-discovery broadcast.
        """
        if ip is not None:
            with self._lock:
                if node_id not in self._nodes:
                    self._nodes[node_id] = RemoteSwarmNode(
                        node_id=node_id,
                        ip=ip,
                        port=port,
                        send_fn=self._send_json,
                    )
                else:
                    self._nodes[node_id].ip = ip
                    self._nodes[node_id].port = port
                node = self._nodes[node_id]

            # Immediately send a PING so the Slave starts streaming 20Hz telemetry to us
            node.ping()
            time.sleep(0.1)
            return node

        print(f"[OpenSwarm Master] Waiting for Slave '{node_id}' on UDP port {self.discovery_port}...")
        start = time.time()
        while (time.time() - start) < timeout:
            with self._lock:
                if node_id in self._nodes:
                    node = self._nodes[node_id]
                    node.ping()
                    print(
                        f"[OpenSwarm Master] Discovered '{node.node_id}' ({node.board}) "
                        f"at {node.ip}:{node.port} | Actuators: {node.declared_actuators} | Sensors: {node.declared_sensors}"
                    )
                    return node
            time.sleep(0.05)

        raise TimeoutError(
            f"Could not auto-discover Slave '{node_id}' within {timeout}s. "
            f"Make sure your laptop and ESP32 are on the same Wi-Fi network, or pass ip='192.168.x.x' directly: "
            f"master.connect('{node_id}', ip='192.168.0.118')"
        )

    def discover_all(self, wait_seconds: float = 2.5) -> Dict[str, RemoteSwarmNode]:
        """Listens for `wait_seconds` and returns all discovered Slave nodes on the network."""
        time.sleep(wait_seconds)
        with self._lock:
            return dict(self._nodes)

    @property
    def nodes(self) -> Dict[str, RemoteSwarmNode]:
        with self._lock:
            return dict(self._nodes)

    def close(self) -> None:
        """Stops all connected Slave motors and closes Master sockets."""
        self._running = False
        with self._lock:
            for node in self._nodes.values():
                try:
                    node.stop()
                except Exception:
                    pass
        try:
            self._cmd_sock.close()
        except Exception:
            pass
        if self._disc_sock:
            try:
                self._disc_sock.close()
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Internal UDP Transport & Background Threads
    # -------------------------------------------------------------------------
    def _send_json(self, ip: str, port: int, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        try:
            self._cmd_sock.sendto(raw, (ip, port))
        except OSError:
            pass

    def _network_loop(self) -> None:
        while self._running:
            # 1. Check Discovery Socket (HELLO broadcasts on port 4211)
            if self._disc_sock is not None:
                try:
                    data, addr = self._disc_sock.recvfrom(2048)
                    self._handle_packet(data, addr)
                except socket.timeout:
                    pass
                except OSError:
                    pass

            # 2. Check Command/Telemetry Socket (STATE telemetry packets)
            try:
                data, addr = self._cmd_sock.recvfrom(2048)
                self._handle_packet(data, addr)
            except socket.timeout:
                pass
            except OSError:
                pass

    def _handle_packet(self, data: bytes, addr: tuple) -> None:
        try:
            msg = json.loads(data.decode("utf-8", errors="ignore"))
        except Exception:
            return

        pkt_type = msg.get("type")
        node_id = msg.get("node")
        if not node_id:
            return

        sender_ip = msg.get("ip") or addr[0]
        sender_port = int(msg.get("port") or SWARM_DEFAULT_SLAVE_PORT)

        with self._lock:
            if pkt_type == "HELLO":
                board = msg.get("board", "UNKNOWN")
                actuators = msg.get("actuators", [])
                sensors = msg.get("sensors", [])
                if node_id not in self._nodes:
                    node = RemoteSwarmNode(
                        node_id=node_id,
                        ip=sender_ip,
                        port=sender_port,
                        send_fn=self._send_json,
                        board=board,
                        actuators=actuators,
                        sensors=sensors,
                    )
                    self._nodes[node_id] = node
                    # Trigger initial PING so Slave starts streaming STATE
                    node.ping()
                else:
                    self._nodes[node_id]._update_hello(sender_ip, sender_port, board, actuators, sensors)

            elif pkt_type == "STATE":
                uptime_ms = int(msg.get("uptime_ms", 0))
                sensors_dict = msg.get("sensors", {})
                if node_id not in self._nodes:
                    self._nodes[node_id] = RemoteSwarmNode(
                        node_id=node_id,
                        ip=addr[0],
                        port=addr[1],
                        send_fn=self._send_json,
                        sensors=list(sensors_dict.keys()),
                    )
                self._nodes[node_id]._update_state(uptime_ms, sensors_dict)

    def _heartbeat_loop(self) -> None:
        while self._running:
            with self._lock:
                nodes_list = list(self._nodes.values())
            for node in nodes_list:
                node.ping()
            time.sleep(self.heartbeat_sec)
