"""
RemoteSwarmNode — Represents a single connected Slave node (ESP32, UNO, Nano, RP2040, or Linux SBC).
Exposes clean Python methods to read live sensors and command any actuator, pin, or bus protocol.
"""

import time
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
        self._sensor_values: Dict[str, Union[float, List[float]]] = {}
        self.uptime_ms: int = 0
        self.last_seen: float = time.time()

    # -------------------------------------------------------------------------
    # Internal state updates (called by SwarmMaster background thread)
    # -------------------------------------------------------------------------
    def _update_hello(self, ip: str, port: int, board: str, actuators: List[str], sensors: List[str]) -> None:
        self.ip = ip
        self.port = port
        self.board = board
        self.declared_actuators = actuators
        self.declared_sensors = sensors
        self.last_seen = time.time()

    def _update_state(self, uptime_ms: int, sensors_dict: Dict[str, Any]) -> None:
        self.uptime_ms = uptime_ms
        self._sensor_values.update(sensors_dict)
        self.last_seen = time.time()

    # -------------------------------------------------------------------------
    # Sensor Reading API
    # -------------------------------------------------------------------------
    @property
    def sensors(self) -> Dict[str, Union[float, List[float]]]:
        """Returns a dictionary of the latest 20Hz streamed sensor values."""
        return dict(self._sensor_values)

    def read(self, sensor_name: str, default: Any = 0.0) -> Union[float, List[float]]:
        """Reads the latest value of a named sensor (e.g., node.read('rssi') or node.read('front_sonar'))."""
        return self._sensor_values.get(sensor_name, default)

    @property
    def is_online(self) -> bool:
        """Returns True if we heard from this Slave within the last 2.0 seconds."""
        return (time.time() - self.last_seen) < 2.0

    # -------------------------------------------------------------------------
    # Pin & GPIO Control API
    # -------------------------------------------------------------------------
    def digital_write(self, name: str, state: Union[int, bool]) -> None:
        """
        Writes HIGH (1/True) or LOW (0/False) to a registered digital output pin
        (e.g., node.digital_write('led', 1)).
        """
        val = 1 if state else 0
        self._send_fn(self.ip, self.port, {"cmd": "ACT", "name": name, "value": val})

    def pwm_write(self, name_or_pin: Union[str, int], duty: int) -> None:
        """
        Writes a PWM duty cycle (0..255) either to a registered PWM output name
        or directly to a raw hardware pin number.
        """
        duty_clamped = max(0, min(255, int(duty)))
        if isinstance(name_or_pin, int):
            self._send_fn(self.ip, self.port, {"cmd": "PIN", "pin": name_or_pin, "value": duty_clamped, "pwm": 1})
        else:
            self._send_fn(self.ip, self.port, {"cmd": "ACT", "name": name_or_pin, "value": duty_clamped})

    def pin_write(self, pin: int, value: Union[int, bool], pwm: bool = False) -> None:
        """
        Direct raw GPIO pin control by pin number (even if not registered in setup()).
        Example: node.pin_write(2, 1) -> sets GPIO 2 HIGH.
        """
        val = int(value)
        self._send_fn(
            self.ip,
            self.port,
            {"cmd": "PIN", "pin": int(pin), "value": val, "pwm": 1 if pwm else 0},
        )

    # -------------------------------------------------------------------------
    # Motor, Servo & Stepper Control API
    # -------------------------------------------------------------------------
    def drive(self, name: str, left: int, right: int = 0) -> None:
        """
        Drives a dual H-Bridge (L298N / DRV8833) or single 2-pin DC motor (-255 to +255).
        Example: node.drive('drive', left=180, right=180)
        """
        self._send_fn(
            self.ip,
            self.port,
            {"cmd": "ACT", "name": name, "left": int(left), "right": int(right)},
        )

    def servo(self, name: str, angle: int) -> None:
        """
        Sets a hobby servo angle (0 to 180 degrees).
        Example: node.servo('gripper_servo', 90)
        """
        self._send_fn(
            self.ip,
            self.port,
            {"cmd": "ACT", "name": name, "angle": int(angle)},
        )

    def stepper(self, name: str, steps: int, step_delay_us: int = 800) -> None:
        """
        Commands a Step/Dir stepper driver (positive = forward, negative = reverse).
        Example: node.stepper('lifter_step', steps=200, step_delay_us=800)
        """
        self._send_fn(
            self.ip,
            self.port,
            {"cmd": "ACT", "name": name, "steps": int(steps), "v2": int(step_delay_us)},
        )

    def stop(self) -> None:
        """Immediately stops all motors on this Slave node."""
        self._send_fn(self.ip, self.port, {"cmd": "STOP"})

    # -------------------------------------------------------------------------
    # Universal Bus & Custom Actuator API (LoRa, SPI, I2C, UART, Custom)
    # -------------------------------------------------------------------------
    def send_bus(self, name: str, data: str = "", v1: int = 0, v2: int = 0) -> None:
        """
        Transmits a string payload or numeric values over a registered LoRa, UART, or Custom actuator.
        Example: node.send_bus('lora_radio', data='HELLO_SWARM')
        """
        self._send_fn(
            self.ip,
            self.port,
            {"cmd": "ACT", "name": name, "v1": int(v1), "v2": int(v2), "data": str(data)},
        )

    def write_reg(self, name: str, reg: int, val: int) -> None:
        """
        Writes a register byte [reg, val] to a registered I2C or SPI actuator device.
        Example: node.write_reg('i2c_pwm_chip', reg=0x06, val=128)
        """
        self._send_fn(
            self.ip,
            self.port,
            {"cmd": "ACT", "name": name, "reg": int(reg), "val": int(val)},
        )

    def set_actuator(self, name: str, v1: int = 0, v2: int = 0, data: str = "") -> None:
        """Generic low-level actuator command."""
        payload: Dict[str, Any] = {"cmd": "ACT", "name": name, "v1": int(v1), "v2": int(v2)}
        if data:
            payload["data"] = data
        self._send_fn(self.ip, self.port, payload)

    def ping(self) -> None:
        """Sends a heartbeat PING to request immediate telemetry and reset the Slave watchdog."""
        self._send_fn(self.ip, self.port, {"cmd": "PING"})

    def __repr__(self) -> str:
        return (
            f"<RemoteSwarmNode id='{self.node_id}' board='{self.board}' "
            f"ip='{self.ip}:{self.port}' actuators={self.declared_actuators} "
            f"sensors={self.declared_sensors}>"
        )
