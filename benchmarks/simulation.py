"""Discrete-event transport around the real master and Linux node code.

No sockets, real sleeps, background threads, or physical-board timing. Board
labels specify roles/clock offsets, not emulation of processor instructions.
"""

import heapq
import json
import math
import socket
import time
from collections import deque
from contextlib import ExitStack
from unittest.mock import patch

from openswarm.master import SwarmMaster
from openswarm_slave.hal_linux import LinuxHAL
from openswarm_slave.node import SwarmNode


class Clock:
    def __init__(self):
        self.us = 100_000_000

    def monotonic(self):
        return self.us / 1e6


class NullThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass

    def join(self, *args, **kwargs):
        pass

    def is_alive(self):
        return False


class MemorySocket:
    def __init__(self, send=None):
        self.incoming = deque()
        self.send = send

    def setsockopt(self, *args):
        pass

    def setblocking(self, *args):
        pass

    def bind(self, *args):
        pass

    def ioctl(self, *args):
        pass

    def close(self):
        pass

    def sendto(self, data, address):
        if self.send:
            self.send(data, address)
        return len(data)

    def recvfrom(self, count):
        if not self.incoming:
            raise BlockingIOError()
        return self.incoming.popleft()


class Simulation:
    def __init__(self):
        self.clock = Clock()
        self.events = []
        self.serial = 0
        self.slaves = {}
        self.execution = []
        self.command_counts = {"ACT": 0, "PING": 0, "STOP": 0}
        self.state_count = 0
        self.master_cpu_ns = 0
        self.rx_latency_ms = []
        self.rtt_samples_ms = []
        self.stack = ExitStack()

    def __enter__(self):
        self.stack.enter_context(patch("time.monotonic", self.clock.monotonic))
        # Only construction is patched; real SDK serialization/dispatch and
        # receive/drain handlers execute in the measured paths.
        with patch("openswarm.master.socket.socket", side_effect=lambda *a, **k: MemorySocket()), patch("openswarm.master.threading.Thread", NullThread):
            self.master = SwarmMaster(discovery_port=0)
        self.master._cmd_sock.send = self.send_command
        return self

    def __exit__(self, *exc):
        self.master.close()
        self.stack.close()

    def event(self, when_us, callback):
        self.serial += 1
        heapq.heappush(self.events, (int(when_us), self.serial, callback))

    def until(self, when_us):
        while self.events and self.events[0][0] <= when_us:
            when, _, callback = heapq.heappop(self.events)
            self.clock.us = when
            callback()
        self.clock.us = int(when_us)

    def add_node(self, node_id, offset_ms, port, tick_ms=1.0, actuator_names=("servo",)):
        node = SwarmNode(node_id, port, hal=LinuxHAL(verbose_sim=False, backend="sim"))
        node._start_time = self.clock.monotonic() - offset_ms / 1000.0
        endpoint = {"node": node, "initial_uptime_ms": offset_ms,
                    "offset_ms": -node._start_time * 1000.0, "port": port,
                    "tick_us": round(tick_ms * 1000), "forward_us": 3000, "reverse_us": 3000}
        self.slaves[port] = endpoint
        node._sock = MemorySocket(lambda raw, addr: self.send_state(endpoint, raw))
        for name in actuator_names:
            def record(v1, v2, data, name=name):
                self.execution.append({"node": node_id, "name": name, "value": v1,
                                       "time_us": self.clock.us, "data": data})
            node.register_custom_actuator(name, record)
        hello = {"type": "HELLO", "node": node_id, "board": "SIMULATED_ROLE",
                 "port": port, "max_command_bytes": 1024,
                 "actuators": list(actuator_names), "sensors": []}
        self.master._handle_packet(json.dumps(hello).encode(), ("127.0.0.1", port))
        return endpoint

    def send_command(self, raw, address):
        endpoint = self.slaves[address[1]]
        packet = json.loads(raw)
        cmd = packet["cmd"]
        self.command_counts[cmd] = self.command_counts.get(cmd, 0) + 1
        def deliver():
            node = endpoint["node"]
            node._sock.incoming.append((raw, ("127.0.0.1", 40000)))
            node._handle_incoming()
            self.schedule_tick(endpoint)
        self.event(self.clock.us + endpoint["forward_us"], deliver)

    def schedule_tick(self, endpoint):
        node = endpoint["node"]
        deadlines = [item["due_mono"] for item in node._pending_actuations.values()]
        deadlines += list(node._active_leases.values())
        if not deadlines:
            return
        period = endpoint["tick_us"]
        deadline_us = round(min(deadlines) * 1e6)
        tick_us = math.ceil(max(self.clock.us + 1, deadline_us) / period) * period
        def tick():
            node._run_due_actuations(self.clock.monotonic())
            self.schedule_tick(endpoint)
        self.event(tick_us, tick)

    def send_state(self, endpoint, raw):
        def deliver():
            self.master._cmd_sock.incoming.append((raw, ("127.0.0.1", endpoint["port"])))
            remote = self.master.get(endpoint["node"].node_id)
            ack = json.loads(raw).get("ack")
            fresh_rtt = ack in remote._pending_pings
            wall = time.perf_counter_ns()
            cpu = time.process_time_ns()
            self.master._drain_socket(self.master._cmd_sock)
            self.master_cpu_ns += time.process_time_ns() - cpu
            self.rx_latency_ms.append((time.perf_counter_ns() - wall) / 1e6)
            self.state_count += 1
            if fresh_rtt and remote.rtt_ms is not None:
                self.rtt_samples_ms.append(remote.rtt_ms)
        self.event(self.clock.us + endpoint["reverse_us"], deliver)

    def calibrate(self):
        for _ in range(3):
            for endpoint in self.slaves.values():
                self.master.subscribe(endpoint["node"].node_id)
                self.master.get(endpoint["node"].node_id).ping()
            self.until(self.clock.us + 10000)
        assert all(self.master.get(e["node"].node_id).clock_offset_ms is not None for e in self.slaves.values())
