#!/usr/bin/env python3
"""
===============================================================================
OpenSwarm HydraArm — Joint 2 (SHOULDER) + Joint 4 (GRIPPER) Slave Node
                     Raspberry Pi running Ubuntu 24.04 Server
===============================================================================
Target Board : Raspberry Pi (RPi 4 / RPi 5 / RPi Zero 2 W) running Ubuntu 24.04 Server
Node ID      : "arm_rpi"
Joint Roles  :
  1. Joint 2 (Shoulder Pitch, 20..160 deg, Home = 140 deg) -> Actuator: "shoulder_servo"
  2. Joint 4 (Gripper Claw,   10..95 deg,  Home = 45 deg)  -> Actuator: "gripper_servo"

WIRING (2× SG90 / MG90S Servos -> Raspberry Pi 40-Pin Header):
  [Shoulder Pitch Servo — Joint 2]
    - Orange/Yellow (Signal) -> BCM GPIO 14 (Physical Pin 8)
    - Red           (VCC 5V) -> Physical Pin 2 (5V Power)
    - Brown/Black   (GND)    -> Physical Pin 6 (GND)

  [Gripper Claw Servo — Joint 4]
    - Orange/Yellow (Signal) -> BCM GPIO 18 (Physical Pin 12)
    - Red           (VCC 5V) -> Physical Pin 4 (5V Power)
    - Brown/Black   (GND)    -> Physical Pin 14 (GND)

  (Note: Physical Pins 4, 6, 8, 12, 14 are all right next to each other on the
   outer edge of the Raspberry Pi header!)

Core Rule:
  - This Slave script ONLY declares Node ID and attached hardware pins/sensors.
  - Zero control logic lives on the Raspberry Pi! All control runs on the
    Linux PC Master.
===============================================================================
"""

import argparse
import os
import sys

# Ensure local `slaves/linux` package in the cloned repo is always importable
# (even when run with `sudo python3` where user site-packages isn't on sys.path)
REPO_LINUX_SLAVE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "slaves", "linux"))
if os.path.isdir(REPO_LINUX_SLAVE) and REPO_LINUX_SLAVE not in sys.path:
    sys.path.insert(0, REPO_LINUX_SLAVE)

from openswarm_slave import SwarmNode


class Ubuntu24DualServoHAL:
    """
    Manages 50 Hz (500..2400 us) servo PWM on Ubuntu 24.04 Raspberry Pi
    across multiple BCM GPIO pins using native lgpio or RPi.GPIO (python3-rpi-lgpio).
    """

    def __init__(self):
        self.mode = "sim"
        self.gpio = None
        self.lgpio = None
        self.handle = None
        self.pwms = {}

        # 1. Try RPi.GPIO (provided by python3-rpi-lgpio on Ubuntu 24.04)
        try:
            import RPi.GPIO as GPIO  # type: ignore

            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            self.gpio = GPIO
            self.mode = "rpi_gpio"
            print("[RPi Servo HAL] Using RPi.GPIO (python3-rpi-lgpio) @ 50Hz")
            return
        except Exception:
            pass

        # 2. Fallback to native lgpio (works on both Raspberry Pi 5 gpiochip4 and RPi 4 gpiochip0)
        try:
            import lgpio  # type: ignore

            for chip in (4, 0):
                try:
                    self.handle = lgpio.gpiochip_open(chip)
                    self.lgpio = lgpio
                    self.mode = "lgpio"
                    print(f"[RPi Servo HAL] Using native lgpio (gpiochip{chip}) @ 50Hz")
                    return
                except Exception:
                    continue
        except Exception as exc:
            print(f"[RPi Servo HAL] Running in simulation mode ({exc})")

    def make_writer(self, label: str, bcm_pin: int, phys_pin: int, default_angle: int):
        if self.mode == "rpi_gpio" and self.gpio is not None:
            self.gpio.setup(bcm_pin, self.gpio.OUT)
            pwm = self.gpio.PWM(bcm_pin, 50)
            init_pulse = int(500 + (default_angle / 180.0) * 1900)
            pwm.start((init_pulse / 20000.0) * 100.0)
            self.pwms[bcm_pin] = pwm
        elif self.mode == "lgpio" and self.lgpio is not None and self.handle is not None:
            self.lgpio.gpio_claim_output(self.handle, bcm_pin, 0)
            init_pulse = int(500 + (default_angle / 180.0) * 1900)
            self.lgpio.tx_servo(self.handle, bcm_pin, init_pulse, 50, 0, 0)

        print(
            f"[RPi Servo HAL] Attached {label:<15} -> BCM GPIO {bcm_pin} (Physical Pin {phys_pin}) "
            f"[Default: {default_angle} deg]"
        )

        def write_servo(v1: int, _v2: int, _data: str) -> None:
            angle = max(0, min(180, int(v1)))
            pulse_us = int(500 + (angle / 180.0) * 1900)  # 500 us (0 deg) .. 2400 us (180 deg)
            duty_pct = (pulse_us / 20000.0) * 100.0      # 2.5% .. 12.0% at 50 Hz
            if self.mode == "lgpio" and self.lgpio is not None and self.handle is not None:
                self.lgpio.tx_servo(self.handle, bcm_pin, pulse_us, 50, 0, 0)
            elif self.mode == "rpi_gpio" and bcm_pin in self.pwms:
                self.pwms[bcm_pin].ChangeDutyCycle(duty_pct)
            print(f"  [{label:<14} BCM {bcm_pin}] -> {angle:3d} deg ({pulse_us} us @ 50Hz)")

        return write_servo


def main() -> None:
    parser = argparse.ArgumentParser(description="HydraArm — RPi Dual Servo Slave Node (Shoulder + Gripper)")
    parser.add_argument("--id", type=str, default="arm_gripper_rpi", help="Unique Slave Node ID")
    parser.add_argument(
        "--shoulder-pin",
        type=int,
        default=14,
        help="BCM GPIO pin for Shoulder Servo (default: 14 / Physical Pin 8)",
    )
    parser.add_argument(
        "--gripper-pin",
        type=int,
        default=18,
        help="BCM GPIO pin for Gripper Servo (default: 18 / Physical Pin 12)",
    )
    parser.add_argument("--port", type=int, default=4210, help="UDP command port (default: 4210)")
    args = parser.parse_args()

    node = SwarmNode(node_id=args.id, udp_port=args.port)
    servo_hal = Ubuntu24DualServoHAL()

    gripper_writer = servo_hal.make_writer("Gripper Claw", args.gripper_pin, 12, default_angle=45)
    shoulder_writer = servo_hal.make_writer("Shoulder Pitch", args.shoulder_pin, 8, default_angle=140)

    # Declare attached hardware ONLY — Zero Control Logic!
    node.register_custom_actuator("shoulder_servo", shoulder_writer)
    node.register_custom_actuator("gripper_servo", gripper_writer)
    node.register_custom_actuator("servo", gripper_writer)  # Backward-compatible alias
    node.register_cpu_temp("cpu_temp")             # RPi CPU temperature (C)
    node.register_system_load("sys_load")          # RPi [1m_load, ram_%]
    node.register_wifi_rssi("rssi")                # Wi-Fi signal strength (dBm)

    node.start(block=True)


if __name__ == "__main__":
    main()
