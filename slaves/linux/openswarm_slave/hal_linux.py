"""
Linux Hardware Abstraction Layer (`LinuxHAL`)
Supports:
- Arduino UNO Q (Linux + MCU bridge / sysfs / libgpiod)
- Arduino Portenta X8 (NXP i.MX 8M Mini Linux sysfs / libgpiod / I2C / SPI / UART)
- Raspberry Pi (RPi.GPIO / libgpiod / sysfs / I2C / SPI / UART)
- Nvidia Jetson (Jetson.GPIO / sysfs / I2C / SPI / UART)
- Generic Linux Laptop / Desktop (sysfs thermal/network + virtual GPIO simulation for testing)
"""

import os
import platform
import socket
import struct
import time
from typing import Any, Dict, List, Optional, Tuple


class LinuxHAL:
    def __init__(self, verbose_sim: bool = True):
        self.verbose_sim = verbose_sim
        self.board_name = self._detect_board()
        self._gpio_backend = "sim"
        self._rpi_gpio = None
        self._lgpio = None
        self._lgpio_handle: Optional[int] = None
        self._pwm_instances: Dict[int, Any] = {}
        self._servo_instances: Dict[int, Any] = {}
        self._sim_pins: Dict[int, int] = {}
        self._i2c_buses: Dict[int, Any] = {}
        self._spi_devs: Dict[Tuple[int, int], Any] = {}
        self._uart_ports: Dict[str, Any] = {}

        self._init_gpio_backend()

    # -------------------------------------------------------------------------
    # Board & Network Detection
    # -------------------------------------------------------------------------
    @staticmethod
    def _detect_board() -> str:
        model_paths = ["/proc/device-tree/model", "/sys/firmware/devicetree/base/model"]
        for p in model_paths:
            if os.path.exists(p):
                try:
                    with open(p, "rb") as f:
                        model = f.read().decode("utf-8", errors="ignore").strip("\x00\r\n ").upper()
                    if "UNO Q" in model or "ARDUINO UNO" in model:
                        return "ARDUINO_UNO_Q"
                    if "PORTENTA" in model or "X8" in model:
                        return "PORTENTA_X8"
                    if "RASPBERRY PI" in model:
                        return "RASPBERRY_PI"
                    if "JETSON" in model or "NVIDIA" in model:
                        return "NVIDIA_JETSON"
                    if model:
                        return model.replace(" ", "_")[:24]
                except Exception:
                    pass

        uname = platform.uname()
        if uname.system == "Linux":
            return f"LINUX_{uname.machine.upper()}"
        return f"{uname.system.upper()}_{uname.machine.upper()}"

    @staticmethod
    def local_ip() -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    @classmethod
    def broadcast_ip(cls) -> str:
        ip = cls.local_ip()
        parts = ip.split(".")
        if len(parts) == 4 and parts[0] != "127":
            return f"{parts[0]}.{parts[1]}.{parts[2]}.255"
        return "255.255.255.255"

    # -------------------------------------------------------------------------
    # GPIO / PWM Backend Initialization (RPi.GPIO / rpi-lgpio -> lgpio -> sysfs -> Sim)
    # -------------------------------------------------------------------------
    def _init_gpio_backend(self) -> None:
        # 1. Prefer native lgpio (pick the 40-pin header chip with >= 28 lines)
        try:
            import lgpio  # type: ignore

            for chip in (4, 0, 1, 2):
                try:
                    h = lgpio.gpiochip_open(chip)
                    info = lgpio.gpio_get_chip_info(h)
                    lines = info[1] if isinstance(info, (list, tuple)) and len(info) > 1 else 0
                    if lines >= 28:
                        self._lgpio_handle = h
                        self._lgpio = lgpio
                        self._gpio_backend = "lgpio"
                        return
                    lgpio.gpiochip_close(h)
                except Exception:
                    continue
        except Exception:
            pass

        # 2. Fallback to RPi.GPIO (or python3-rpi-lgpio on Ubuntu 24.04)
        try:
            import RPi.GPIO as GPIO  # type: ignore

            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            self._rpi_gpio = GPIO
            self._gpio_backend = "rpi_gpio"
            return
        except Exception:
            pass

        if os.path.exists("/sys/class/gpio"):
            self._gpio_backend = "sysfs"
        else:
            self._gpio_backend = "sim"

    def setup_pin(self, pin: int, mode: str = "OUT", pullup: bool = False) -> None:
        if pin < 0 or pin == 255:
            return
        if self._gpio_backend == "rpi_gpio" and self._rpi_gpio is not None:
            if mode == "OUT":
                self._rpi_gpio.setup(pin, self._rpi_gpio.OUT)
                self._rpi_gpio.output(pin, self._rpi_gpio.LOW)
            else:
                pud = self._rpi_gpio.PUD_UP if pullup else self._rpi_gpio.PUD_OFF
                self._rpi_gpio.setup(pin, self._rpi_gpio.IN, pull_up_down=pud)
        elif self._gpio_backend == "lgpio" and self._lgpio is not None and self._lgpio_handle is not None:
            try:
                if mode == "OUT":
                    self._lgpio.gpio_claim_output(self._lgpio_handle, pin, 0)
                else:
                    flags = self._lgpio.SET_PULL_UP if pullup else 0
                    self._lgpio.gpio_claim_input(self._lgpio_handle, pin, flags)
            except Exception:
                pass
        elif self._gpio_backend == "sysfs":
            gpio_dir = f"/sys/class/gpio/gpio{pin}"
            if not os.path.exists(gpio_dir):
                try:
                    with open("/sys/class/gpio/export", "w") as f:
                        f.write(str(pin))
                except Exception:
                    pass
            try:
                with open(f"{gpio_dir}/direction", "w") as f:
                    f.write("out" if mode == "OUT" else "in")
            except Exception:
                pass
        else:
            self._sim_pins[pin] = 0

    def digital_write(self, pin: int, value: int) -> None:
        if pin < 0 or pin == 255:
            return
        v = 1 if value > 0 else 0
        if self._gpio_backend == "rpi_gpio" and self._rpi_gpio is not None:
            self._rpi_gpio.output(pin, self._rpi_gpio.HIGH if v else self._rpi_gpio.LOW)
        elif self._gpio_backend == "lgpio" and self._lgpio is not None and self._lgpio_handle is not None:
            try:
                self._lgpio.gpio_write(self._lgpio_handle, pin, v)
            except Exception:
                pass
        elif self._gpio_backend == "sysfs":
            try:
                with open(f"/sys/class/gpio/gpio{pin}/value", "w") as f:
                    f.write("1" if v else "0")
            except Exception:
                pass
        else:
            prev = self._sim_pins.get(pin)
            self._sim_pins[pin] = v
            if self.verbose_sim and prev != v:
                print(f"  [LinuxHAL] GPIO Pin {pin} -> {'HIGH (1)' if v else 'LOW  (0)'}")

    def digital_read(self, pin: int, pullup: bool = False) -> float:
        if pin < 0 or pin == 255:
            return 0.0
        if self._gpio_backend == "rpi_gpio" and self._rpi_gpio is not None:
            raw = int(self._rpi_gpio.input(pin))
            return float(1 - raw if pullup else raw)
        elif self._gpio_backend == "lgpio" and self._lgpio is not None and self._lgpio_handle is not None:
            try:
                raw = int(self._lgpio.gpio_read(self._lgpio_handle, pin))
                return float(1 - raw if pullup else raw)
            except Exception:
                return 0.0
        elif self._gpio_backend == "sysfs":
            try:
                with open(f"/sys/class/gpio/gpio{pin}/value", "r") as f:
                    raw = int(f.read().strip())
                return float(1 - raw if pullup else raw)
            except Exception:
                return 0.0
        return float(self._sim_pins.get(pin, 0))

    def pwm_write(self, pin: int, duty_255: int) -> None:
        if pin < 0 or pin == 255:
            return
        d = max(0, min(255, int(duty_255)))
        if self._gpio_backend == "rpi_gpio" and self._rpi_gpio is not None:
            if pin not in self._pwm_instances:
                self._rpi_gpio.setup(pin, self._rpi_gpio.OUT)
                pwm = self._rpi_gpio.PWM(pin, 1000)
                pwm.start(0)
                self._pwm_instances[pin] = pwm
            self._pwm_instances[pin].ChangeDutyCycle((d / 255.0) * 100.0)
        elif self._gpio_backend == "lgpio" and self._lgpio is not None and self._lgpio_handle is not None:
            self._lgpio.tx_pwm(self._lgpio_handle, pin, 1000, (d / 255.0) * 100.0)
        else:
            prev = self._sim_pins.get(pin)
            self._sim_pins[pin] = d
            if self.verbose_sim and prev != d:
                print(f"  [LinuxHAL] PWM Pin {pin} -> duty {d}/255")

    def servo_write(self, pin: int, angle: int) -> None:
        """
        Writes a standard 50 Hz hobby servo angle (0..180 deg -> 500..2400 us pulse width).
        Works on Raspberry Pi running Ubuntu 24.04 Server (via rpi-lgpio or lgpio).
        """
        if pin < 0 or pin == 255:
            return
        ang = max(0, min(180, int(angle)))
        pulse_us = int(500 + (ang / 180.0) * 1900)  # 500 us (0 deg) .. 2400 us (180 deg)
        duty_pct = (pulse_us / 20000.0) * 100.0      # 2.5% .. 12.0% at 50 Hz (20,000 us period)

        if self._gpio_backend == "rpi_gpio" and self._rpi_gpio is not None:
            if pin not in self._servo_instances:
                self._rpi_gpio.setup(pin, self._rpi_gpio.OUT)
                pwm = self._rpi_gpio.PWM(pin, 50)
                pwm.start(duty_pct)
                self._servo_instances[pin] = pwm
            else:
                self._servo_instances[pin].ChangeDutyCycle(duty_pct)
        elif self._gpio_backend == "lgpio" and self._lgpio is not None and self._lgpio_handle is not None:
            try:
                self._lgpio.gpio_claim_output(self._lgpio_handle, pin, 0)
            except Exception:
                pass
            self._lgpio.tx_servo(self._lgpio_handle, pin, pulse_us, 50, 0, 12)
        else:
            prev = self._sim_pins.get(pin)
            self._sim_pins[pin] = ang
            if self.verbose_sim and prev != ang:
                print(f"  [LinuxHAL] SERVO Pin {pin} -> {ang} deg ({pulse_us} us @ 50Hz)")

    # -------------------------------------------------------------------------
    # H-Bridge Motor Helpers
    # -------------------------------------------------------------------------
    def drive_hbridge_3pin(self, ena: int, in1: int, in2: int, speed: int) -> None:
        s = max(-255, min(255, int(speed)))
        if s > 0:
            self.digital_write(in1, 1)
            self.digital_write(in2, 0)
            self.pwm_write(ena, s)
        elif s < 0:
            self.digital_write(in1, 0)
            self.digital_write(in2, 1)
            self.pwm_write(ena, -s)
        else:
            self.digital_write(in1, 0)
            self.digital_write(in2, 0)
            self.pwm_write(ena, 0)

    def drive_hbridge_2pin(self, in1: int, in2: int, speed: int) -> None:
        s = max(-255, min(255, int(speed)))
        if s > 0:
            self.pwm_write(in1, s)
            self.pwm_write(in2, 0)
        elif s < 0:
            self.pwm_write(in1, 0)
            self.pwm_write(in2, -s)
        else:
            self.pwm_write(in1, 0)
            self.pwm_write(in2, 0)

    # -------------------------------------------------------------------------
    # I2C / SPI / UART Bus Helpers
    # -------------------------------------------------------------------------
    def _get_i2c(self, bus_num: int = 1):
        if bus_num not in self._i2c_buses:
            try:
                import smbus2  # type: ignore

                self._i2c_buses[bus_num] = smbus2.SMBus(bus_num)
            except Exception:
                self._i2c_buses[bus_num] = None
        return self._i2c_buses[bus_num]

    def i2c_write_reg(self, bus_num: int, i2c_addr: int, reg: int, val: int) -> None:
        bus = self._get_i2c(bus_num)
        if bus is not None:
            try:
                bus.write_byte_data(i2c_addr, reg & 0xFF, val & 0xFF)
                return
            except Exception:
                pass
        if self.verbose_sim:
            print(f"  [LinuxHAL] I2C(bus={bus_num}, addr=0x{i2c_addr:02X}) write reg 0x{reg:02X} = 0x{val:02X}")

    def i2c_read_bytes(self, bus_num: int, i2c_addr: int, reg: int, length: int) -> List[int]:
        bus = self._get_i2c(bus_num)
        if bus is not None:
            try:
                return list(bus.read_i2c_block_data(i2c_addr, reg & 0xFF, length))
            except Exception:
                pass
        return [0] * length

    def _get_uart(self, port_path: str, baud: int):
        if port_path not in self._uart_ports:
            try:
                import serial  # type: ignore

                self._uart_ports[port_path] = serial.Serial(port_path, baudrate=baud, timeout=0.01)
            except Exception:
                self._uart_ports[port_path] = None
        return self._uart_ports[port_path]

    def uart_write(self, port_path: str, baud: int, data_str: str, fallback_byte: int = 0) -> None:
        ser = self._get_uart(port_path, baud)
        if ser is not None:
            try:
                if data_str:
                    ser.write((data_str + "\n").encode("utf-8"))
                else:
                    ser.write(bytes([fallback_byte & 0xFF]))
                return
            except Exception:
                pass
        if self.verbose_sim:
            print(f"  [LinuxHAL] UART({port_path} @ {baud}) TX -> '{data_str or fallback_byte}'")

    def uart_read_float(self, port_path: str, baud: int, last_val: float = 0.0) -> float:
        ser = self._get_uart(port_path, baud)
        if ser is not None and ser.in_waiting > 0:
            try:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    return float(line)
            except Exception:
                pass
        return last_val

    # -------------------------------------------------------------------------
    # Built-in Linux System & Sensor Readers
    # -------------------------------------------------------------------------
    @staticmethod
    def read_cpu_temp() -> float:
        paths = [
            "/sys/class/thermal/thermal_zone0/temp",
            "/sys/devices/virtual/thermal/thermal_zone0/temp",
        ]
        for p in paths:
            if os.path.exists(p):
                try:
                    with open(p, "r") as f:
                        return float(f.read().strip()) / 1000.0
                except Exception:
                    pass
        return 42.0

    @staticmethod
    def read_system_load() -> List[float]:
        load_1m = 0.0
        ram_pct = 0.0
        if os.path.exists("/proc/loadavg"):
            try:
                with open("/proc/loadavg", "r") as f:
                    load_1m = float(f.read().split()[0])
            except Exception:
                pass
        if os.path.exists("/proc/meminfo"):
            try:
                mem: Dict[str, int] = {}
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        parts = line.split(":")
                        if len(parts) == 2:
                            mem[parts[0].strip()] = int(parts[1].strip().split()[0])
                total = mem.get("MemTotal", 0)
                avail = mem.get("MemAvailable", mem.get("MemFree", 0))
                if total > 0:
                    ram_pct = ((total - avail) / float(total)) * 100.0
            except Exception:
                pass
        return [round(load_1m, 2), round(ram_pct, 1)]

    @staticmethod
    def read_wifi_rssi() -> float:
        if os.path.exists("/proc/net/wireless"):
            try:
                with open("/proc/net/wireless", "r") as f:
                    lines = f.readlines()
                if len(lines) >= 3:
                    parts = lines[2].split()
                    if len(parts) >= 4:
                        val = float(parts[3].rstrip("."))
                        return val if val < 0 else val - 100.0
            except Exception:
                pass
        return -50.0

    def read_ultrasonic(self, trig: int, echo: int) -> float:
        if self._gpio_backend == "sim":
            return 25.0
        self.digital_write(trig, 0)
        time.sleep(0.000002)
        self.digital_write(trig, 1)
        time.sleep(0.000010)
        self.digital_write(trig, 0)

        timeout = time.perf_counter() + 0.015
        while self.digital_read(echo) == 0:
            if time.perf_counter() > timeout:
                return -1.0
        start = time.perf_counter()
        while self.digital_read(echo) == 1:
            if time.perf_counter() > timeout:
                return -1.0
        duration_us = (time.perf_counter() - start) * 1_000_000.0
        return round((duration_us * 0.0343) * 0.5, 2)

    def read_mpu6050(self, bus_num: int, i2c_addr: int) -> List[float]:
        raw = self.i2c_read_bytes(bus_num, i2c_addr, 0x3B, 14)
        if any(raw):
            ax, ay, az, _, gx, gy, gz = struct.unpack(">hhhhhhh", bytes(raw))
            return [
                round(ax / 16384.0, 2),
                round(ay / 16384.0, 2),
                round(az / 16384.0, 2),
                round(gx / 131.0, 2),
                round(gy / 131.0, 2),
                round(gz / 131.0, 2),
            ]
        return [0.0, 0.0, 1.0, 0.0, 0.0, 0.0]

    def read_lsm6dsox(self, bus_num: int, i2c_addr: int) -> List[float]:
        raw = self.i2c_read_bytes(bus_num, i2c_addr, 0x22, 12)
        if any(raw):
            gx, gy, gz, ax, ay, az = struct.unpack("<hhhhhh", bytes(raw))
            return [
                round(ax * 0.000061, 2),
                round(ay * 0.000061, 2),
                round(az * 0.000061, 2),
                round(gx * 0.00875, 2),
                round(gy * 0.00875, 2),
                round(gz * 0.00875, 2),
            ]
        return [0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
