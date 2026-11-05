"""
SwarmNode (Linux Slave Agent)
=============================
Identical Hardware Declaration API & UDP Wire Protocol (4210 / 4211) to the C++ Arduino library.
Supports both Pythonic `snake_case` and Arduino `camelCase` registration methods!
"""

import json
import socket
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Union

from .hal_linux import LinuxHAL

SWARM_DEFAULT_PORT = 4210
SWARM_DISCOVERY_PORT = 4211
SWARM_WATCHDOG_SEC = 0.50   # 500ms hardware safety watchdog
SWARM_TELEMETRY_SEC = 0.05  # 20 Hz sensor telemetry stream
SWARM_HELLO_SEC = 1.00      # 1 Hz discovery broadcast


class SwarmNode:
    def __init__(self, node_id: str, udp_port: int = SWARM_DEFAULT_PORT, verbose_sim: bool = True):
        self.node_id = node_id
        self.udp_port = udp_port
        self.hal = LinuxHAL(verbose_sim=verbose_sim)

        self._actuators: Dict[str, Dict[str, Any]] = {}
        self._sensors: Dict[str, Dict[str, Any]] = {}

        self._master_addr: Optional[ tuple ] = None
        self._last_master_pkt = 0.0
        self._watchdog_tripped = False
        self._start_time = time.time()
        self._running = False
        self._sock: Optional[socket.socket] = None

    # -------------------------------------------------------------------------
    # 1. Standard Actuator Registration API (Motors, Servos, Steppers, GPIO)
    # -------------------------------------------------------------------------
    def register_l298n(self, name: str, ena: int, in1: int, in2: int, enb: int, in3: int, in4: int) -> bool:
        for p in (ena, in1, in2, enb, in3, in4):
            self.hal.setup_pin(p, "OUT")
        self._actuators[name] = {"type": "L298N", "pins": [ena, in1, in2, enb, in3, in4]}
        return True

    def register_drv8833(self, name: str, in1: int, in2: int, in3: int, in4: int) -> bool:
        for p in (in1, in2, in3, in4):
            self.hal.setup_pin(p, "OUT")
        self._actuators[name] = {"type": "DRV8833", "pins": [in1, in2, in3, in4]}
        return True

    def register_motor_2pin(self, name: str, pin_a: int, pin_b: int) -> bool:
        self.hal.setup_pin(pin_a, "OUT")
        self.hal.setup_pin(pin_b, "OUT")
        self._actuators[name] = {"type": "MOTOR_2PIN", "pins": [pin_a, pin_b]}
        return True

    def register_servo(self, name: str, pin: int) -> bool:
        self.hal.setup_pin(pin, "OUT")
        self._actuators[name] = {"type": "SERVO", "pins": [pin]}
        return True

    def register_stepper(self, name: str, step_pin: int, dir_pin: int, en_pin: int = 255) -> bool:
        self.hal.setup_pin(step_pin, "OUT")
        self.hal.setup_pin(dir_pin, "OUT")
        if en_pin != 255:
            self.hal.setup_pin(en_pin, "OUT")
        self._actuators[name] = {"type": "STEPPER", "pins": [step_pin, dir_pin, en_pin]}
        return True

    def register_digital_output(self, name: str, pin: int) -> bool:
        self.hal.setup_pin(pin, "OUT")
        self._actuators[name] = {"type": "DIGITAL_OUT", "pins": [pin]}
        return True

    def register_pwm_output(self, name: str, pin: int) -> bool:
        self.hal.setup_pin(pin, "OUT")
        self._actuators[name] = {"type": "PWM_OUT", "pins": [pin]}
        return True

    def register_pin(self, name: str, pin: int, mode: str = "OUT", pullup: bool = False) -> bool:
        if mode.upper().startswith("IN"):
            return self.register_digital_input(name, pin, pullup=pullup)
        return self.register_digital_output(name, pin)

    # -------------------------------------------------------------------------
    # 2. Standard Sensor Registration API
    # -------------------------------------------------------------------------
    def register_ultrasonic(self, name: str, trig_pin: int, echo_pin: int) -> bool:
        self.hal.setup_pin(trig_pin, "OUT")
        self.hal.setup_pin(echo_pin, "IN")
        self._sensors[name] = {"type": "ULTRASONIC", "pins": [trig_pin, echo_pin]}
        return True

    def register_bumper(self, name: str, pin: int, pullup: bool = True) -> bool:
        return self.register_digital_input(name, pin, pullup=pullup)

    def register_ir_sensor(self, name: str, pin: int, pullup: bool = False) -> bool:
        return self.register_digital_input(name, pin, pullup=pullup)

    def register_digital_input(self, name: str, pin: int, pullup: bool = False) -> bool:
        self.hal.setup_pin(pin, "IN", pullup=pullup)
        self._sensors[name] = {"type": "DIGITAL_IN", "pins": [pin], "pullup": pullup}
        return True

    def register_mpu6050(self, name: str, i2c_addr: int = 0x68, bus_num: int = 1) -> bool:
        self.hal.i2c_write_reg(bus_num, i2c_addr, 0x6B, 0x00)
        self._sensors[name] = {"type": "MPU6050", "bus": bus_num, "addr": i2c_addr}
        return True

    def register_lsm6dsox(self, name: str, i2c_addr: int = 0x6A, bus_num: int = 1) -> bool:
        self.hal.i2c_write_reg(bus_num, i2c_addr, 0x10, 0x40)
        self.hal.i2c_write_reg(bus_num, i2c_addr, 0x11, 0x40)
        self._sensors[name] = {"type": "LSM6DSOX", "bus": bus_num, "addr": i2c_addr}
        return True

    def register_cpu_temp(self, name: str = "cpu_temp") -> bool:
        self._sensors[name] = {"type": "CPU_TEMP"}
        return True

    def register_system_load(self, name: str = "sys_load") -> bool:
        self._sensors[name] = {"type": "SYS_LOAD"}
        return True

    def register_wifi_rssi(self, name: str = "rssi") -> bool:
        self._sensors[name] = {"type": "WIFI_RSSI"}
        return True

    # -------------------------------------------------------------------------
    # 3. Universal Bus Protocols & Custom Callbacks (I2C, SPI, UART, Custom)
    # -------------------------------------------------------------------------
    def register_generic_i2c(self, name: str, i2c_addr: int, reg_addr: int, num_bytes: int = 2, bus_num: int = 1) -> bool:
        self._sensors[name] = {
            "type": "GENERIC_I2C",
            "bus": bus_num,
            "addr": i2c_addr,
            "reg": reg_addr,
            "len": num_bytes,
        }
        return True

    def register_i2c_actuator(self, name: str, i2c_addr: int, bus_num: int = 1) -> bool:
        self._actuators[name] = {"type": "I2C_BUS", "bus": bus_num, "addr": i2c_addr}
        return True

    def register_uart_sensor(self, name: str, port: str = "/dev/ttyUSB0", baud: int = 9600) -> bool:
        self._sensors[name] = {"type": "UART_BUS", "port": port, "baud": baud, "last": 0.0}
        return True

    def register_uart_actuator(self, name: str, port: str = "/dev/ttyUSB0", baud: int = 9600) -> bool:
        self._actuators[name] = {"type": "UART_BUS", "port": port, "baud": baud}
        return True

    def register_custom_sensor(self, name: str, read_callback: Callable[[], Union[float, List[float]]]) -> bool:
        self._sensors[name] = {"type": "CUSTOM", "fn": read_callback}
        return True

    def register_custom_actuator(self, name: str, write_callback: Callable[[int, int, str], None]) -> bool:
        self._actuators[name] = {"type": "CUSTOM", "fn": write_callback}
        return True

    # -------------------------------------------------------------------------
    # Arduino C++ camelCase Aliases (So sketches translate 1:1!)
    # -------------------------------------------------------------------------
    registerL298N = register_l298n
    registerDRV8833 = register_drv8833
    registerMotor2Pin = register_motor_2pin
    registerServo = register_servo
    registerStepper = register_stepper
    registerDigitalOutput = register_digital_output
    registerPWMOutput = register_pwm_output
    registerPin = register_pin
    registerUltrasonic = register_ultrasonic
    registerBumper = register_bumper
    registerIRSensor = register_ir_sensor
    registerDigitalInput = register_digital_input
    registerMPU6050 = register_mpu6050
    registerLSM6DSOX = register_lsm6dsox
    registerWiFiRSSI = register_wifi_rssi
    registerGenericI2C = register_generic_i2c
    registerI2CActuator = register_i2c_actuator
    registerUARTSensor = register_uart_sensor
    registerUARTActuator = register_uart_actuator
    registerCustomSensor = register_custom_sensor
    registerCustomActuator = register_custom_actuator

    # -------------------------------------------------------------------------
    # 4. Start Background Daemon
    # -------------------------------------------------------------------------
    def start(self, block: bool = True) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_BROADCAST"):
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.bind(("0.0.0.0", self.udp_port))
        self._sock.settimeout(0.01)

        self._running = True
        self._last_master_pkt = time.time()

        ip = self.hal.local_ip()
        print("==========================================================")
        print(f" OpenSwarm Linux Slave Node : '{self.node_id}'")
        print(f" Detected Platform          : {self.hal.board_name} (GPIO: {self.hal._gpio_backend})")
        print(f" Local IP & UDP Port        : {ip}:{self.udp_port}")
        print(f" Registered Actuators       : {list(self._actuators.keys())}")
        print(f" Registered Sensors         : {list(self._sensors.keys())}")
        print(" Advertising to Linux Master on UDP Port 4211...")
        print("==========================================================")

        daemon = threading.Thread(target=self._background_loop, daemon=True, name="SwarmLinuxSlave")
        daemon.start()

        if block:
            try:
                while self._running:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                print("\n[SwarmNode] Stopping motors and shutting down Linux Slave...")
                self.stop()

    def stop(self) -> None:
        self._running = False
        self._emergency_stop_all()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Core Runtime Loop (Discovery, Telemetry, Command Execution, Watchdog)
    # -------------------------------------------------------------------------
    def _background_loop(self) -> None:
        last_telemetry = 0.0
        last_hello = 0.0

        while self._running:
            now = time.time()

            # 1. Handle Incoming Master Commands
            self._handle_incoming()

            # 2. 500ms Hardware Safety Watchdog
            if self._master_addr is not None and (now - self._last_master_pkt > SWARM_WATCHDOG_SEC):
                if not self._watchdog_tripped:
                    self._emergency_stop_all()
                    self._watchdog_tripped = True
                    print("[SwarmNode] WATCHDOG: Master timeout -> Motors stopped.")

            # 3. 20 Hz Sensor Telemetry Stream
            if self._master_addr is not None and (now - last_telemetry >= SWARM_TELEMETRY_SEC):
                last_telemetry = now
                self._send_telemetry()

            # 4. 1 Hz Auto-Discovery Broadcast
            if now - last_hello >= SWARM_HELLO_SEC:
                last_hello = now
                self._send_hello()

    def _handle_incoming(self) -> None:
        if not self._sock:
            return
        try:
            data, addr = self._sock.recvfrom(1024)
        except socket.timeout:
            return
        except OSError:
            return

        try:
            msg = json.loads(data.decode("utf-8", errors="ignore"))
        except Exception:
            return

        cmd = msg.get("cmd")
        if not cmd:
            return

        self._master_addr = addr
        self._last_master_pkt = time.time()
        self._watchdog_tripped = False

        if cmd == "PING":
            self._send_telemetry()
        elif cmd == "STOP":
            self._emergency_stop_all()
        elif cmd == "PIN":
            pin = int(msg.get("pin", -1))
            val = int(msg.get("value", 0))
            pwm = int(msg.get("pwm", 0))
            if pin >= 0:
                if pwm > 0:
                    self.hal.pwm_write(pin, val)
                else:
                    self.hal.setup_pin(pin, "OUT")
                    self.hal.digital_write(pin, val)
        elif cmd == "ACT":
            name = msg.get("name", "")
            act = self._actuators.get(name)
            if not act:
                return

            v1 = int(
                msg.get(
                    "value",
                    msg.get(
                        "state",
                        msg.get("left", msg.get("angle", msg.get("steps", msg.get("reg", msg.get("v1", 0))))),
                    ),
                )
            )
            v2 = int(msg.get("right", msg.get("val", msg.get("v2", 0))))
            data_str = str(msg.get("data", ""))
            self._execute_actuator(act, v1, v2, data_str)

    def _execute_actuator(self, act: Dict[str, Any], v1: int, v2: int, data_str: str) -> None:
        t = act["type"]
        pins = act.get("pins", [])
        if t == "L298N":
            self.hal.drive_hbridge_3pin(pins[0], pins[1], pins[2], v1)
            self.hal.drive_hbridge_3pin(pins[3], pins[4], pins[5], v2)
        elif t == "DRV8833":
            self.hal.drive_hbridge_2pin(pins[0], pins[1], v1)
            self.hal.drive_hbridge_2pin(pins[2], pins[3], v2)
        elif t == "MOTOR_2PIN":
            self.hal.drive_hbridge_2pin(pins[0], pins[1], v1)
        elif t == "DIGITAL_OUT":
            self.hal.digital_write(pins[0], 1 if v1 > 0 else 0)
        elif t == "PWM_OUT" or t == "SERVO":
            self.hal.pwm_write(pins[0], v1)
        elif t == "I2C_BUS":
            self.hal.i2c_write_reg(act["bus"], act["addr"], v1, v2)
        elif t == "UART_BUS":
            self.hal.uart_write(act["port"], act["baud"], data_str, v1)
        elif t == "CUSTOM":
            act["fn"](v1, v2, data_str)

    def _read_sensor(self, sens: Dict[str, Any]) -> Union[float, List[float]]:
        t = sens["type"]
        if t == "CPU_TEMP":
            return self.hal.read_cpu_temp()
        if t == "SYS_LOAD":
            return self.hal.read_system_load()
        if t == "WIFI_RSSI":
            return self.hal.read_wifi_rssi()
        if t == "DIGITAL_IN":
            return self.hal.digital_read(sens["pins"][0], sens.get("pullup", False))
        if t == "ULTRASONIC":
            return self.hal.read_ultrasonic(sens["pins"][0], sens["pins"][1])
        if t == "MPU6050":
            return self.hal.read_mpu6050(sens["bus"], sens["addr"])
        if t == "LSM6DSOX":
            return self.hal.read_lsm6dsox(sens["bus"], sens["addr"])
        if t == "GENERIC_I2C":
            raw = self.hal.i2c_read_bytes(sens["bus"], sens["addr"], sens["reg"], sens["len"])
            val = 0
            for b in raw:
                val = (val << 8) | b
            return float(val)
        if t == "UART_BUS":
            sens["last"] = self.hal.uart_read_float(sens["port"], sens["baud"], sens.get("last", 0.0))
            return sens["last"]
        if t == "CUSTOM":
            return sens["fn"]()
        return 0.0

    def _send_hello(self) -> None:
        if not self._sock:
            return
        payload = {
            "type": "HELLO",
            "node": self.node_id,
            "board": self.hal.board_name,
            "ip": self.hal.local_ip(),
            "port": self.udp_port,
            "actuators": list(self._actuators.keys()),
            "sensors": list(self._sensors.keys()),
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        try:
            self._sock.sendto(raw, (self.hal.broadcast_ip(), SWARM_DISCOVERY_PORT))
        except Exception:
            pass

    def _send_telemetry(self) -> None:
        if not self._sock or self._master_addr is None:
            return
        uptime_ms = int((time.time() - self._start_time) * 1000)
        sensor_readings: Dict[str, Any] = {}
        for name, sens in self._sensors.items():
            sensor_readings[name] = self._read_sensor(sens)

        payload = {
            "type": "STATE",
            "node": self.node_id,
            "uptime_ms": uptime_ms,
            "sensors": sensor_readings,
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        try:
            self._sock.sendto(raw, self._master_addr)
        except Exception:
            pass

    def _emergency_stop_all(self) -> None:
        for act in self._actuators.values():
            if act["type"] in ("L298N", "DRV8833", "MOTOR_2PIN", "STEPPER"):
                self._execute_actuator(act, 0, 0, "")
