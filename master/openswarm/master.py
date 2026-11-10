"""
SwarmMaster — Central Linux/Cross-Platform Master Engine for OpenSwarm.
- Listens on UDP Port 4211 for Slave auto-discovery broadcasts ("HELLO").
- Sends low-latency actuator commands and 5 Hz watchdog heartbeats ("PING") over UDP Port 4210.
- Receives 20 Hz sensor telemetry streams ("STATE") from all connected Slaves in a background
  thread that waits on both sockets with select() and drains every queued packet (low latency).
"""

import json
import logging
import math
import select
import socket
import sys
import threading
import time
from typing import Any, Dict, Optional

from .node import RemoteSwarmNode
from .protocol import decode_packet, integer, sensor_values, source_ip

logger = logging.getLogger(__name__)

SWARM_DEFAULT_SLAVE_PORT = 4210
SWARM_DISCOVERY_PORT = 4211
SWARM_HEARTBEAT_SEC = 0.20  # 200ms keepalive (well below the 500ms Slave hardware watchdog)


def _disable_udp_connreset(sock: socket.socket) -> None:
    """
    On Windows, sending a UDP packet to an offline host makes the NEXT recvfrom()
    raise WSAECONNRESET (10054). Disable that behaviour so one offline Slave
    cannot disturb telemetry from the others. No-op on Linux/macOS.
    """
    if sys.platform.startswith("win") and hasattr(socket, "SIO_UDP_CONNRESET"):
        try:
            sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        except (OSError, ValueError):
            pass


class SwarmMaster:
    def __init__(self, discovery_port: int = SWARM_DISCOVERY_PORT, heartbeat_sec: float = SWARM_HEARTBEAT_SEC):
        self.discovery_port = discovery_port
        self.heartbeat_sec = heartbeat_sec
        self._nodes: Dict[str, RemoteSwarmNode] = {}
        self._active_nodes = set()
        self._lock = threading.Lock()
        self._running = True
        self._closed = False
        self._stop_event = threading.Event()
        if not math.isfinite(heartbeat_sec) or heartbeat_sec <= 0:
            raise ValueError("heartbeat_sec must be positive")

        # 1. Command & Telemetry Socket (ephemeral port; Slaves reply with STATE to this socket)
        self._cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._cmd_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            # Larger receive buffer so bursts from many Slaves are never dropped
            self._cmd_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        except OSError:
            pass
        self._cmd_sock.bind(("0.0.0.0", 0))
        self._cmd_sock.setblocking(False)
        _disable_udp_connreset(self._cmd_sock)

        # 2. Discovery Socket (listens on UDP 4211 for Slave HELLO broadcasts)
        self._disc_sock: Optional[socket.socket] = None
        try:
            self._disc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._disc_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_BROADCAST"):
                self._disc_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._disc_sock.bind(("0.0.0.0", self.discovery_port))
            self._disc_sock.setblocking(False)
        except OSError:
            # If another process is already bound to 4211, direct IP connect still works
            if self._disc_sock is not None:
                self._disc_sock.close()
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
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        if self._closed:
            raise RuntimeError("Master is closed")
        deadline = time.monotonic() + timeout
        if ip is not None:
            ip = source_ip(ip)
            port = integer(port, 1, 65535)
            with self._lock:
                if node_id not in self._nodes:
                    self._nodes[node_id] = RemoteSwarmNode(
                        node_id=node_id,
                        ip=ip,
                        port=port,
                        send_fn=self._sender(node_id),
                    )
                else:
                    self._nodes[node_id].ip = ip
                    self._nodes[node_id].port = port
                node = self._nodes[node_id]
                node._state_received.clear()
        else:
            node = None
        awaiting = None
        while time.monotonic() < deadline and not self._closed:
            with self._lock:
                node = self._nodes.get(node_id)
            if node is not None:
                if node is not awaiting:
                    node._state_received.clear()
                    awaiting = node
                node.ping()
                if node._state_received.wait(min(self.heartbeat_sec, max(0, deadline - time.monotonic()))):
                    return node
            else:
                self._stop_event.wait(min(0.05, max(0, deadline - time.monotonic())))
        with self._lock:
            self._active_nodes.discard(node_id)
        raise TimeoutError(
            f"No telemetry from Slave '{node_id}' within {timeout}s. "
            "Check the node ID, address, command port, and network connectivity."
        )

    def _sender(self, node_id):
        def send(ip, port, payload):
            if self._closed:
                raise RuntimeError("Master is closed")
            if payload.get("cmd") in ("PING", "ACT", "PIN"):
                with self._lock:
                    node = self._nodes[node_id]
                    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
                    if len(encoded) > node.max_command_bytes:
                        raise ValueError("Command exceeds node's advertised datagram limit")
                    self._active_nodes.add(node_id)
            self._send_json(ip, port, payload)
        return send

    def subscribe(self, node_id: str) -> Optional[RemoteSwarmNode]:
        """Request telemetry/keepalive for a discovered node without blocking.

        Discovery and get() are passive. connect(), subscribe(), or the first
        actuator command opt a node into this master's active session.
        """
        if self._closed:
            raise RuntimeError("Master is closed")
        with self._lock:
            node = self._nodes.get(node_id)
            active = node_id in self._active_nodes
        if node is not None and not active:
            node.ping()
        return node

    def disconnect(self, node_id: str) -> None:
        """Stop an active node and stop renewing its keepalive."""
        with self._lock:
            active = node_id in self._active_nodes
            self._active_nodes.discard(node_id)
            node = self._nodes.get(node_id)
        if active and node is not None:
            node.stop()

    def discover_all(self, wait_seconds: float = 2.5) -> Dict[str, RemoteSwarmNode]:
        """Listens for `wait_seconds` and returns all discovered Slave nodes on the network."""
        time.sleep(wait_seconds)
        with self._lock:
            return dict(self._nodes)

    @property
    def nodes(self) -> Dict[str, RemoteSwarmNode]:
        with self._lock:
            return dict(self._nodes)

    def get(self, node_id: str) -> Optional[RemoteSwarmNode]:
        """Returns an already-known Slave node by ID (or None) without waiting."""
        with self._lock:
            return self._nodes.get(node_id)

    def stop_all(self, include_discovered: bool = False) -> None:
        """Send STOP to active nodes, optionally including passive discoveries."""
        with self._lock:
            nodes_list = [node for key, node in self._nodes.items()
                          if include_discovered or key in self._active_nodes]
        for node in nodes_list:
            node.stop()

    def close(self) -> None:
        """Stops all connected Slave motors and closes Master sockets."""
        if self._closed:
            return
        self._running = False
        self._stop_event.set()
        # Join heartbeat before STOP so shutdown cannot renew a stopped node.
        if self._hb_thread is not threading.current_thread():
            self._hb_thread.join(timeout=1.0)
        with self._lock:
            for node_id in self._active_nodes:
                node = self._nodes[node_id]
                try:
                    node.stop()
                except Exception:
                    pass
            self._active_nodes.clear()
        self._closed = True
        try:
            self._cmd_sock.close()
        except Exception:
            pass
        if self._disc_sock:
            try:
                self._disc_sock.close()
            except Exception:
                pass
        if self._rx_thread is not threading.current_thread():
            self._rx_thread.join(timeout=1.0)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    # -------------------------------------------------------------------------
    # Internal UDP Transport & Background Threads
    # -------------------------------------------------------------------------
    def _send_json(self, ip: str, port: int, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload, separators=(",", ":"), allow_nan=False, ensure_ascii=False).encode("utf-8")
        try:
            self._cmd_sock.sendto(raw, (ip, port))
        except OSError as exc:
            logger.debug("UDP send to %s:%s failed: %s", ip, port, exc)

    def _network_loop(self) -> None:
        """
        Waits on BOTH sockets at once with select() and drains every queued packet
        before waiting again. This keeps telemetry latency at ~1 ms regardless of
        how many Slaves are streaming (the previous round-robin recv with a 50 ms
        timeout per socket capped throughput at ~20 packets/s in total).
        """
        while self._running:
            socks = [self._cmd_sock]
            if self._disc_sock is not None:
                socks.append(self._disc_sock)
            try:
                readable, _, _ = select.select(socks, [], [], 0.1)
            except (OSError, ValueError):
                # Socket closed during shutdown
                if not self._running:
                    return
                time.sleep(0.01)
                continue

            for sock in readable:
                self._drain_socket(sock)

    def _drain_socket(self, sock: socket.socket) -> None:
        """Reads all currently queued datagrams from a socket without blocking."""
        for _ in range(512):  # upper bound so one flooding socket cannot starve the other
            try:
                data, addr = sock.recvfrom(4096)
            except (BlockingIOError, socket.timeout):
                return
            except OSError:
                # Socket closed during shutdown -> stop. Otherwise (e.g. Windows
                # WSAECONNRESET after sending to an offline Slave) ignore & continue.
                if not self._running:
                    return
                continue
            try:
                self._handle_packet(data, addr)
            except Exception:
                logger.exception("Unexpected packet processing failure from %s", addr)

    def _handle_packet(self, data: bytes, addr: tuple) -> None:
        try:
            msg = decode_packet(data)
        except (UnicodeDecodeError, ValueError, RecursionError):
            logger.debug("Ignoring malformed UDP packet from %s", addr)
            return

        if not isinstance(msg, dict):
            logger.debug("Ignoring non-object UDP packet from %s", addr)
            return

        pkt_type = msg.get("type")
        node_id = msg.get("node")
        if pkt_type not in ("HELLO", "STATE") or not isinstance(node_id, str) or not node_id:
            return

        try:
            sender_ip = source_ip(addr[0])
            sender_port = integer(msg.get("port", SWARM_DEFAULT_SLAVE_PORT), 1, 65535)
        except (TypeError, ValueError, OverflowError):
            logger.debug("Ignoring packet with invalid port from %s", addr)
            return
        if not 1 <= sender_port <= 65535:
            logger.debug("Ignoring packet with out-of-range port from %s", addr)
            return

        with self._lock:
            if pkt_type == "HELLO":
                try:
                    command_limit = integer(msg.get("max_command_bytes", 159), 14, 4096)
                except ValueError:
                    return
                board = msg.get("board", "UNKNOWN")
                actuators = msg.get("actuators", [])
                sensors = msg.get("sensors", [])
                if (
                    not isinstance(board, str)
                    or not isinstance(actuators, list)
                    or not all(isinstance(item, str) for item in actuators)
                    or not isinstance(sensors, list)
                    or not all(isinstance(item, str) for item in sensors)
                ):
                    logger.debug("Ignoring HELLO with invalid metadata from %s", addr)
                    return
                if node_id not in self._nodes:
                    node = RemoteSwarmNode(
                        node_id=node_id,
                        ip=sender_ip,
                        port=sender_port,
                        send_fn=self._sender(node_id),
                        board=board,
                        actuators=actuators,
                        sensors=sensors,
                    )
                    self._nodes[node_id] = node
                    node._update_hello(sender_ip, sender_port, board, actuators, sensors)
                else:
                    self._nodes[node_id]._update_hello(sender_ip, sender_port, board, actuators, sensors)
                self._nodes[node_id].is_virtual = msg.get("virtual") is True
                self._nodes[node_id].max_command_bytes = command_limit
                capabilities = msg.get("capabilities", {})
                if isinstance(capabilities, dict):
                    self._nodes[node_id].capabilities = dict(capabilities)

            elif pkt_type == "STATE":
                try:
                    uptime_ms = integer(msg.get("uptime_ms", 0))
                    sensors_dict = sensor_values(msg.get("sensors", {}))
                except (TypeError, ValueError, OverflowError):
                    logger.debug("Ignoring STATE with invalid uptime from %s", addr)
                    return
                sensors_dict = msg.get("sensors", {})
                if not isinstance(sensors_dict, dict):
                    logger.debug("Ignoring STATE with invalid sensors from %s", addr)
                    return
                if node_id not in self._nodes:
                    self._nodes[node_id] = RemoteSwarmNode(
                        node_id=node_id,
                        ip=addr[0],
                        port=addr[1],
                        send_fn=self._sender(node_id),
                        sensors=list(sensors_dict.keys()),
                    )
                node = self._nodes[node_id]
                if node.ip != addr[0] or node.port != addr[1]:
                    return
                node._update_state(uptime_ms, sensors_dict)
                errors = msg.get("sensor_errors", {})
                if isinstance(errors, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in errors.items()):
                    node.sensor_errors = dict(errors)

    def _heartbeat_loop(self) -> None:
        while self._running:
            with self._lock:
                nodes_list = [self._nodes[k] for k in self._active_nodes]
            for node in nodes_list:
                node.ping()
            self._stop_event.wait(self.heartbeat_sec)
