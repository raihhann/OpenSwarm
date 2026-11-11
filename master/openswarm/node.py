"""
RemoteSwarmNode — Represents a single connected Slave node (ESP32, UNO, Nano, RP2040, or Linux SBC).
Exposes clean Python methods to read live sensors and command any actuator, pin, or bus protocol.
"""

import time
import copy
import json
import threading
from .protocol import sequence_is_newer
from typing import Any, Callable, Dict, List, Optional, Union


class RemoteSwarmNode:
    def __init__(
        self,
        node_id: str,
        ip: str,
        port: int,
        send_fn: Callable[[str, int, Dict[str, Any]], None],
        board: str = "UNKNOWN",
        actuators: Optional[List[str]] = None,
        sensors: Optional[List[str]] = None,
    ):
        self.node_id: str = node_id
        self.ip: str = ip
        self.port: int = port
        self.board: str = board
        self.declared_actuators: List[str] = actuators or []
        self.declared_sensors: List[str] = sensors or []

        self._send_fn = send_fn
        self._state_lock = threading.RLock()
        self._tx_lock = threading.RLock()
        self._sensor_values: Dict[str, Union[float, List[float]]] = {}
        self.uptime_ms: int = 0
        self.last_seen: float = 0.0
        self.last_telemetry: float = 0.0
        self._seen_at: Optional[float] = None
        self._telemetry_at: Optional[float] = None
        self._state_received = threading.Event()
        self.sensor_errors: Dict[str, str] = {}
        self.is_virtual = False
        self.capabilities: Dict[str, Any] = {}
        self.max_command_bytes = 159

        # Sequence tracking, RTT / jitter & Master-to-Slave clock offset telemetry
        self._tx_seq: int = 0
        self._pending_pings: Dict[int, float] = {}
        self._clock_probe_seqs = set()
        self._clock_samples = []
        self._clock_sample = None
        self.clock_drift_ppm = 200.0  # Explicit uncertainty-model assumption, not a measured bound.
        self.reordered_states = 0
        self.clock_resets = 0
        self.last_ack_seq: int = 0
        self.rtt_ms: Optional[float] = None
        self.jitter_ms: Optional[float] = None
        self.clock_offset_ms: Optional[float] = None
        self.default_lease_ms: Optional[int] = None
        self.watchdog_trips: int = 0
        self.lease_expirations: int = 0
        self.dropped_out_of_order: int = 0

    def _next_seq(self) -> int:
        with self._state_lock:
            self._tx_seq = (self._tx_seq % 32767) + 1
            seq = self._tx_seq
            if len(self._pending_pings) >= 256:
                oldest_key = next(iter(self._pending_pings))
                self._pending_pings.pop(oldest_key, None)
                self._clock_probe_seqs.discard(oldest_key)
            self._clock_probe_seqs.discard(seq)
            self._pending_pings[seq] = time.monotonic()
            return seq

    def _dispatch(self, payload: Dict[str, Any]) -> None:
        # Allocation and actual send order must agree across heartbeat/control threads.
        with self._tx_lock:
            self._dispatch_locked(payload)

    def _dispatch_locked(self, payload: Dict[str, Any]) -> None:
        seq = self._next_seq()
        if payload.get("cmd") == "PING":
            with self._state_lock:
                self._clock_probe_seqs.add(seq)
        with_seq = {**payload, "seq": seq}
        try:
            encoded = json.dumps(with_seq, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(encoded) <= self.max_command_bytes:
                self._send_fn(self.ip, self.port, with_seq)
                return
        except (TypeError, ValueError):
            pass
        with self._state_lock:
            self._pending_pings.pop(seq, None)
            self._clock_probe_seqs.discard(seq)
        self._send_fn(self.ip, self.port, payload)

    # -------------------------------------------------------------------------
    # Internal state updates (called by SwarmMaster background thread)
    # -------------------------------------------------------------------------
    def _update_hello(self, ip: str, port: int, board: str, actuators: List[str], sensors: List[str]) -> None:
        if self.ip != ip or self.port != port:
            with self._state_lock:
                self._clock_samples.clear()
                self._clock_sample = None
                self.clock_offset_ms = None
                self._telemetry_at = None
                self.last_ack_seq = 0
        self.ip = ip
        self.port = port
        self.board = board
        self.declared_actuators = actuators
        self.declared_sensors = sensors
        self.last_seen = time.time()
        self._seen_at = time.monotonic()

    def _update_state(
        self,
        uptime_ms: int,
        sensors_dict: Dict[str, Any],
        ack: Optional[int] = None,
        wd_trips: Optional[int] = None,
        lease_exp: Optional[int] = None,
        seq_drop: Optional[int] = None,
    ) -> None:
        with self._state_lock:
            return self._update_state_locked(uptime_ms, sensors_dict, ack, wd_trips, lease_exp, seq_drop)

    def _update_state_locked(self, uptime_ms, sensors_dict, ack, wd_trips, lease_exp, seq_drop):
        now_mono = time.monotonic()
        sent_at = self._pending_pings.get(ack)
        is_probe = ack in self._clock_probe_seqs
        if self._telemetry_at is not None and uptime_ms < self.uptime_ms:
            # A reply to a probe sent AFTER the last accepted STATE establishes a
            # fresh lower-uptime epoch. Otherwise this may simply be delayed UDP.
            if not (is_probe and sent_at is not None and sent_at >= self._telemetry_at):
                self.reordered_states += 1
                return False
            self._clock_samples.clear()
            self._clock_sample = None
            self.clock_offset_ms = None
            self.clock_resets += 1
            self.last_ack_seq = 0
        self.uptime_ms = uptime_ms
        # A STATE packet contains the complete sample; don't retain values for omitted sensors.
        self._sensor_values = copy.deepcopy(sensors_dict)
        now = time.time()
        self.last_seen = now
        self.last_telemetry = now
        self._seen_at = now_mono
        self._telemetry_at = now_mono
        if wd_trips is not None:
            if wd_trips > self.watchdog_trips:
                self.last_ack_seq = 0
            self.watchdog_trips = wd_trips
        if lease_exp is not None:
            self.lease_expirations = lease_exp
        if seq_drop is not None:
            self.dropped_out_of_order = seq_drop
        if ack is not None and not isinstance(ack, bool) and isinstance(ack, int) and 1 <= ack <= 32767:
            if sequence_is_newer(ack, self.last_ack_seq):
                self.last_ack_seq = ack
            sent_at = self._pending_pings.pop(ack, None)
            self._clock_probe_seqs.discard(ack)
            # Evict older unacknowledged timestamps that precede this cumulative ack
            stale = [k for k in self._pending_pings if sequence_is_newer(ack, k)]
            for k in stale:
                self._pending_pings.pop(k, None)
                self._clock_probe_seqs.discard(k)
            if sent_at is not None:
                sample_rtt_ms = max(0.0, (now_mono - sent_at) * 1000.0)
                if self.rtt_ms is None:
                    self.rtt_ms = round(sample_rtt_ms, 3)
                    self.jitter_ms = 0.0
                else:
                    diff = abs(sample_rtt_ms - self.rtt_ms)
                    prev_jitter = self.jitter_ms if self.jitter_ms is not None else 0.0
                    self.jitter_ms = round(prev_jitter + (diff - prev_jitter) / 16.0, 3)
                    self.rtt_ms = round(sample_rtt_ms, 3)
                if is_probe:
                    # PING causes immediate STATE. ACT ack can wait for periodic
                    # telemetry and is not a clock-calibration exchange.
                    lower = float(uptime_ms) - now_mono * 1000.0
                    upper = float(uptime_ms) + 1.0 - sent_at * 1000.0
                    self._clock_samples.append((now_mono, lower, upper))
                    self._clock_samples = [s for s in self._clock_samples if now_mono - s[0] <= 5.0][-32:]
                    self._clock_sample = min(self._clock_samples, key=lambda s: s[2] - s[1])
                    self.clock_offset_ms = (self._clock_sample[1] + self._clock_sample[2]) / 2.0
        self._state_received.set()
        return True

    def snapshot(self):
        """One coherent telemetry/clock view for experiments and controllers.

        Bounds assume the PING response timestamp is generated between send and
        receive, 1 ms timestamp quantization and the declared drift allowance.
        They are not an independent calibration of physical clock accuracy.
        """
        with self._state_lock:
            now = time.monotonic()
            self._refresh_clock(now)
            clock = None
            if self._clock_sample is not None:
                at, lower, upper = self._clock_sample
                age = max(0.0, now - at)
                # Timestamp generation can occur anywhere in the exchange;
                # allow drift from send, not only from response receipt.
                exchange_s = max(0.0, upper - lower - 1.0) / 1000.0
                drift = (age + exchange_s) * self.clock_drift_ppm / 1000.0
                clock = dict(offset_ms=self.clock_offset_ms, lower_ms=lower - drift, upper_ms=upper + drift,
                             sample_mono_s=at, age_ms=age * 1000, fresh=age <= 5.0,
                             uncertainty_ms=(upper - lower) / 2 + drift, drift_ppm_assumption=self.clock_drift_ppm)
            return dict(uptime_ms=self.uptime_ms, sensors=copy.deepcopy(self._sensor_values), clock=clock,
                        ack=self.last_ack_seq, rtt_ms=self.rtt_ms, jitter_ms=self.jitter_ms,
                        wd_trips=self.watchdog_trips, lease_exp=self.lease_expirations,
                        seq_drop=self.dropped_out_of_order, reordered_states=self.reordered_states,
                        clock_resets=self.clock_resets)

    def _refresh_clock(self, now):
        recent = [sample for sample in self._clock_samples if now - sample[0] <= 5.0]
        if recent:
            self._clock_samples = recent
            self._clock_sample = min(recent, key=lambda s: s[2] - s[1])
            self.clock_offset_ms = (self._clock_sample[1] + self._clock_sample[2]) / 2.0

    # -------------------------------------------------------------------------
    # Sensor Reading API
    # -------------------------------------------------------------------------
    @property
    def sensors(self) -> Dict[str, Union[float, List[float]]]:
        """Returns a dictionary of the latest 20Hz streamed sensor values."""
        return copy.deepcopy(self._sensor_values)

    def read(self, sensor_name: str, default: Any = 0.0, *, max_age: Optional[float] = None) -> Union[float, List[float]]:
        """Reads the latest value of a named sensor (e.g., node.read('rssi') or node.read('front_sonar'))."""
        if max_age is not None and self.telemetry_age > max_age:
            return default
        return copy.deepcopy(self._sensor_values.get(sensor_name, default))

    @property
    def telemetry_age(self) -> float:
        """Seconds since the last STATE telemetry packet was received (inf if none yet)."""
        if self._telemetry_at is None:
            return float("inf")
        return time.monotonic() - self._telemetry_at

    @property
    def is_online(self) -> bool:
        """Returns True if we heard from this Slave within the last 2.0 seconds."""
        return self._seen_at is not None and (time.monotonic() - self._seen_at) < 2.0

    def slave_time_ms(self, master_mono: Optional[float] = None) -> Optional[int]:
        """Returns estimated Slave uptime_ms at `master_mono` (defaults to time.monotonic()), or None if clock_offset_ms is unknown."""
        with self._state_lock:
            now = time.monotonic()
            self._refresh_clock(now)
            if self.clock_offset_ms is None:
                return None
            if self._clock_sample is not None and now - self._clock_sample[0] > 5.0:
                return None
            t = now if master_mono is None else float(master_mono)
            return max(0, int(round(t * 1000.0 + self.clock_offset_ms)))

    def _with_at_ms(
        self,
        payload: Dict[str, Any],
        at_ms: Optional[int] = None,
        lease_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        if at_ms is not None:
            payload["at_ms"] = int(at_ms) & 0x7FFF
        eff_lease = self.default_lease_ms if lease_ms is None else lease_ms
        if eff_lease is not None:
            if isinstance(eff_lease, bool) or not isinstance(eff_lease, int) or not (1 <= eff_lease <= 30000):
                raise ValueError("lease_ms must be an integer in 1..30000")
            payload["lease_ms"] = int(eff_lease)
        return payload

    # -------------------------------------------------------------------------
    # Pin & GPIO Control API
    # -------------------------------------------------------------------------
    def digital_write(
        self,
        name: str,
        state: Union[int, bool],
        *,
        at_ms: Optional[int] = None,
        lease_ms: Optional[int] = None,
    ) -> None:
        """
        Writes HIGH (1/True) or LOW (0/False) to a registered digital output pin
        (e.g., node.digital_write('led', 1)).
        """
        val = 1 if state else 0
        self._dispatch(self._with_at_ms({"cmd": "ACT", "name": name, "value": val}, at_ms, lease_ms))

    def pwm_write(
        self,
        name_or_pin: Union[str, int],
        duty: int,
        *,
        at_ms: Optional[int] = None,
        lease_ms: Optional[int] = None,
    ) -> None:
        """
        Writes a PWM duty cycle (0..255) either to a registered PWM output name
        or directly to a raw hardware pin number.
        """
        duty_clamped = max(0, min(255, int(duty)))
        if isinstance(name_or_pin, int):
            self._dispatch({"cmd": "PIN", "pin": name_or_pin, "value": duty_clamped, "pwm": 1})
        else:
            self._dispatch(self._with_at_ms({"cmd": "ACT", "name": name_or_pin, "value": duty_clamped}, at_ms, lease_ms))

    def pin_write(self, pin: int, value: Union[int, bool], pwm: bool = False) -> None:
        """
        Direct raw GPIO pin control by pin number (even if not registered in setup()).
        Example: node.pin_write(2, 1) -> sets GPIO 2 HIGH.
        """
        val = int(value)
        self._dispatch({"cmd": "PIN", "pin": int(pin), "value": val, "pwm": 1 if pwm else 0})

    # -------------------------------------------------------------------------
    # Motor, Servo & Stepper Control API
    # -------------------------------------------------------------------------
    def drive(
        self,
        name: str,
        left: int,
        right: int = 0,
        *,
        at_ms: Optional[int] = None,
        lease_ms: Optional[int] = None,
    ) -> None:
        """
        Drives a dual H-Bridge (L298N / DRV8833) or single 2-pin DC motor (-255 to +255).
        Example: node.drive('drive', left=180, right=180)
        """
        self._dispatch(self._with_at_ms({"cmd": "ACT", "name": name, "left": int(left), "right": int(right)}, at_ms, lease_ms))

    def servo(
        self,
        name: str,
        angle: int,
        *,
        at_ms: Optional[int] = None,
        lease_ms: Optional[int] = None,
    ) -> None:
        """
        Sets a hobby servo angle (0 to 180 degrees).
        Example: node.servo('gripper_servo', 90)
        """
        self._dispatch(self._with_at_ms({"cmd": "ACT", "name": name, "angle": int(angle)}, at_ms, lease_ms))

    def stepper(
        self,
        name: str,
        steps: int,
        step_delay_us: int = 800,
        *,
        at_ms: Optional[int] = None,
        lease_ms: Optional[int] = None,
    ) -> None:
        """
        Commands a Step/Dir stepper driver (positive = forward, negative = reverse).
        Example: node.stepper('lifter_step', steps=200, step_delay_us=800)
        """
        self._dispatch(self._with_at_ms({"cmd": "ACT", "name": name, "steps": int(steps), "v2": int(step_delay_us)}, at_ms, lease_ms))

    def stop(self) -> None:
        """Immediately stops all motors on this Slave node."""
        self._dispatch({"cmd": "STOP"})

    # -------------------------------------------------------------------------
    # Universal Bus & Custom Actuator API (UART, SPI, I2C, Custom)
    # -------------------------------------------------------------------------
    def send_bus(
        self,
        name: str,
        data: str = "",
        v1: int = 0,
        v2: int = 0,
        *,
        at_ms: Optional[int] = None,
        lease_ms: Optional[int] = None,
    ) -> None:
        """
        Transmits a string payload or numeric values over a registered UART or Custom actuator.
        Example: node.send_bus('uart_link', data='HELLO_SWARM')
        """
        self._dispatch(self._with_at_ms({"cmd": "ACT", "name": name, "v1": int(v1), "v2": int(v2), "data": str(data)}, at_ms, lease_ms))

    def write_reg(
        self,
        name: str,
        reg: int,
        val: int,
        *,
        at_ms: Optional[int] = None,
        lease_ms: Optional[int] = None,
    ) -> None:
        """
        Writes a register byte [reg, val] to a registered I2C or SPI actuator device.
        Example: node.write_reg('i2c_pwm_chip', reg=0x06, val=128)
        """
        self._dispatch(self._with_at_ms({"cmd": "ACT", "name": name, "reg": int(reg), "val": int(val)}, at_ms, lease_ms))

    def set_actuator(
        self,
        name: str,
        v1: int = 0,
        v2: int = 0,
        data: str = "",
        *,
        at_ms: Optional[int] = None,
        lease_ms: Optional[int] = None,
    ) -> None:
        """Generic low-level actuator command."""
        payload: Dict[str, Any] = {"cmd": "ACT", "name": name, "v1": int(v1), "v2": int(v2)}
        if data:
            payload["data"] = data
        self._dispatch(self._with_at_ms(payload, at_ms, lease_ms))

    def ping(self) -> None:
        """Sends a heartbeat PING to request immediate telemetry and reset the Slave watchdog."""
        self._dispatch({"cmd": "PING"})

    def __repr__(self) -> str:
        return (
            f"<RemoteSwarmNode id='{self.node_id}' board='{self.board}' "
            f"ip='{self.ip}:{self.port}' actuators={self.declared_actuators} "
            f"sensors={self.declared_sensors}>"
        )
