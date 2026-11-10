#!/usr/bin/env python3
"""
===============================================================================
OpenSwarm HydraArm — Joint 2 (SHOULDER) + Joint 4 (GRIPPER) Slave Node
                     Raspberry Pi running Ubuntu 24.04 Server
===============================================================================
Target Board : Raspberry Pi (RPi 4 / RPi 5 / RPi Zero 2 W) running Ubuntu 24.04 Server
Node ID      : "arm_shoulder_gripper_rpi"
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

Core Rule:
  - This Slave script ONLY declares Node ID and attached hardware pins/sensors.
  - Zero control logic lives on the Raspberry Pi! All control runs on the
    Master PC.
===============================================================================
"""

import argparse
import os
import sys
import threading

# Ensure local `slaves/linux` package in the cloned repo is always importable
# (even when run with `sudo python3` where user site-packages isn't on sys.path)
REPO_LINUX_SLAVE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "slaves", "linux"))
if os.path.isdir(REPO_LINUX_SLAVE) and REPO_LINUX_SLAVE not in sys.path:
    sys.path.insert(0, REPO_LINUX_SLAVE)

from openswarm_slave import SwarmNode


class Ubuntu24DualServoHAL:
    """
    Manages jitter-free 50 Hz (500..2400 us) servo PWM on Ubuntu 24.04 Raspberry Pi:
      - Updates lgpio's active servo slot in-place (cycles=0) while moving so its
        5-slot TX queue never overflows, then stops pulses 280 ms after movement
        ends so Linux kernel scheduling jitter never causes idle servo twitching.
    """

    def __init__(self):
        self.mode = "sim"
        self.gpio = None
        self.lgpio = None
        self.handle = None
        self.pwms = {}
        self.stop_timers = {}
        self.last_angles = {}
        self._lock = threading.Lock()

        # 1. Try native lgpio first (pick the 40-pin header chip with >= 28 lines)
        try:
            import lgpio  # type: ignore

            for chip in (4, 0, 1, 2):
                try:
                    h = lgpio.gpiochip_open(chip)
                    info = lgpio.gpio_get_chip_info(h)
                    # info is [status, lines, name, label]; 40-pin header has >= 28 GPIO lines
                    lines = info[1] if isinstance(info, (list, tuple)) and len(info) > 1 else 0
                    if lines >= 28:
                        self.handle = h
                        self.lgpio = lgpio
                        self.mode = "lgpio"
                        print(f"[RPi Servo HAL] Using native lgpio (gpiochip{chip}, {lines} lines) @ 50Hz")
                        return
                    lgpio.gpiochip_close(h)
                except Exception:
                    continue
        except Exception:
            pass

        # 2. Fallback to RPi.GPIO (python3-rpi-lgpio)
        try:
            import RPi.GPIO as GPIO  # type: ignore

            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            self.gpio = GPIO
            self.mode = "rpi_gpio"
            print("[RPi Servo HAL] Using RPi.GPIO (python3-rpi-lgpio) @ 50Hz")
            return
        except Exception as exc:
            print(f"[RPi Servo HAL] Running in simulation mode ({exc})")

    def _idle_pin(self, bcm_pin: int) -> None:
        """Stop software PWM pulses once the servo has reached its target angle so it never shakes at rest."""
        with self._lock:
            self.stop_timers.pop(bcm_pin, None)
            if self.mode == "lgpio" and self.lgpio is not None and self.handle is not None:
                try:
                    # Passing pulse_width=0 to lgpio.tx_servo stops servo pulses cleanly
                    self.lgpio.tx_servo(self.handle, bcm_pin, 0, 50, 0, 0)
                except Exception:
                    pass

    def make_writer(self, label: str, bcm_pin: int, phys_pin: int, default_angle: int):
        init_pulse = int(500 + (default_angle / 180.0) * 1900)
        init_duty = (init_pulse / 20000.0) * 100.0
        self.last_angles[bcm_pin] = default_angle

        if self.mode == "lgpio" and self.lgpio is not None and self.handle is not None:
            try:
                self.lgpio.gpio_free(self.handle, bcm_pin)
            except Exception:
                pass
            self.lgpio.gpio_claim_output(self.handle, bcm_pin, 0)
            # Use cycles=0 so lgpio updates in-place without filling its 5-slot TX queue,
            # then stop pulses after 0.35s via _idle_pin so the servo stays silent at rest
            self.lgpio.tx_servo(self.handle, bcm_pin, init_pulse, 50, 0, 0)
            init_timer = threading.Timer(0.35, self._idle_pin, args=(bcm_pin,))
            init_timer.daemon = True
            self.stop_timers[bcm_pin] = init_timer
            init_timer.start()
        elif self.mode == "rpi_gpio" and self.gpio is not None:
            self.gpio.setup(bcm_pin, self.gpio.OUT)
            pwm = self.gpio.PWM(bcm_pin, 50)
            pwm.start(init_duty)
            self.pwms[bcm_pin] = pwm

        print(
            f"[RPi Servo HAL] Attached {label:<15} -> BCM GPIO {bcm_pin} (Physical Pin {phys_pin}) "
            f"[Default: {default_angle} deg]"
        )

        def write_servo(v1: int, _v2: int, _data: str) -> None:
            angle = max(0, min(180, int(v1)))
            pulse_us = int(500 + (angle / 180.0) * 1900)  # 500 us (0 deg) .. 2400 us (180 deg)
            duty_pct = (pulse_us / 20000.0) * 100.0      # 2.5% .. 12.0% at 50 Hz

            with self._lock:
                # Ignore redundant commands for the exact same angle
                if self.last_angles.get(bcm_pin) == angle:
                    return
                self.last_angles[bcm_pin] = angle

                old_timer = self.stop_timers.pop(bcm_pin, None)
                if old_timer is not None:
                    old_timer.cancel()

                if self.mode == "lgpio" and self.lgpio is not None and self.handle is not None:
                    try:
                        # cycles=0 updates lgpio's active servo slot in-place (never fills TX queue!)
                        self.lgpio.tx_servo(self.handle, bcm_pin, pulse_us, 50, 0, 0)
                    except Exception:
                        try:
                            self.lgpio.tx_servo(self.handle, bcm_pin, 0, 50, 0, 0)
                            self.lgpio.tx_servo(self.handle, bcm_pin, pulse_us, 50, 0, 0)
                        except Exception:
                            pass
                elif self.mode == "rpi_gpio" and bcm_pin in self.pwms:
                    self.pwms[bcm_pin].ChangeDutyCycle(duty_pct)

                # Stop pulses 280 ms after the last movement step completes -> zero idle shake!
                timer = threading.Timer(0.28, self._idle_pin, args=(bcm_pin,))
                timer.daemon = True
                self.stop_timers[bcm_pin] = timer
                timer.start()

            print(f"  [{label:<14} BCM {bcm_pin}] -> {angle:3d} deg ({pulse_us} us @ 50Hz)")

        return write_servo


def main() -> None:
    parser = argparse.ArgumentParser(description="HydraArm — RPi Dual Servo Slave Node (Shoulder + Gripper)")
    parser.add_argument("--id", type=str, default="arm_shoulder_gripper_rpi", help="Unique Slave Node ID")
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
