#!/usr/bin/env python3
"""
===============================================================================
OpenSwarm HydraArm — Joint 4: GRIPPER CLAW Servo Node (Raspberry Pi Ubuntu 24.04)
===============================================================================
Target Board : Raspberry Pi (RPi 4 / RPi 5 / RPi Zero 2 W) running Ubuntu 24.04 Server
Node ID      : "arm_gripper_rpi"
Joint Role   : Geared Parallel Gripper Jaws (10 deg = OPEN, 90 deg = CLOSED)

WIRING (Gripper SG90 / MG90S Servo -> Raspberry Pi 40-Pin Header):
  - Servo Orange/Yellow (Signal) -> BCM GPIO 18 (Physical Pin 12 — Hardware PWM0)
  - Servo Red           (VCC 5V) -> Physical Pin 2 or Pin 4 (5V Power)
  - Servo Brown/Black   (GND)    -> Physical Pin 6 or Pin 14 (GND)

Core Rule:
  - This Slave script ONLY declares Node ID and attached hardware pins/sensors.
  - Zero control logic lives on the Raspberry Pi! All control runs on the
    Linux PC Master.
===============================================================================
"""

import argparse
from openswarm_slave import SwarmNode


def _make_ubuntu24_servo_driver(bcm_pin: int):
    """
    Returns a 50 Hz (500..2400 us) servo writer callback for Ubuntu 24.04 RPi
    using lgpio (RPi 4 / RPi 5) or RPi.GPIO (python3-rpi-lgpio).
    """
    state = {"mode": "sim", "handle": None, "lgpio": None, "pwm": None}

    # 1. Try native lgpio (works on both Raspberry Pi 5 gpiochip4 and RPi 4 gpiochip0)
    try:
        import lgpio  # type: ignore

        for chip in (4, 0):
            try:
                h = lgpio.gpiochip_open(chip)
                lgpio.gpio_claim_output(h, bcm_pin, 0)
                state["mode"] = "lgpio"
                state["handle"] = h
                state["lgpio"] = lgpio
                print(f"[RPi Servo HAL] Using native lgpio (gpiochip{chip}) on BCM GPIO {bcm_pin} @ 50Hz")
                break
            except Exception:
                continue
    except Exception:
        pass

    # 2. Fallback to RPi.GPIO (provided by python3-rpi-lgpio on Ubuntu 24.04)
    if state["mode"] == "sim":
        try:
            import RPi.GPIO as GPIO  # type: ignore

            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(bcm_pin, GPIO.OUT)
            pwm = GPIO.PWM(bcm_pin, 50)
            pwm.start(0)
            state["mode"] = "rpi_gpio"
            state["pwm"] = pwm
            print(f"[RPi Servo HAL] Using RPi.GPIO 50Hz PWM on BCM GPIO {bcm_pin}")
        except Exception as exc:
            print(f"[RPi Servo HAL] Running in simulation mode ({exc})")

    def write_servo(v1: int, _v2: int, _data: str) -> None:
        angle = max(0, min(180, int(v1)))
        pulse_us = int(500 + (angle / 180.0) * 1900)  # 500 us (0 deg) .. 2400 us (180 deg)
        duty_pct = (pulse_us / 20000.0) * 100.0      # 2.5% .. 12.0% at 50 Hz
        if state["mode"] == "lgpio":
            state["lgpio"].tx_servo(state["handle"], bcm_pin, pulse_us, 50, 0, 0)
        elif state["mode"] == "rpi_gpio":
            state["pwm"].ChangeDutyCycle(duty_pct)
        print(f"  [Gripper Servo BCM {bcm_pin}] -> {angle:3d} deg ({pulse_us} us @ 50Hz)")

    return write_servo


def main() -> None:
    parser = argparse.ArgumentParser(description="HydraArm Joint 4 — RPi Gripper Slave Node")
    parser.add_argument("--id", type=str, default="arm_gripper_rpi", help="Unique Slave Node ID")
    parser.add_argument("--servo-pin", type=int, default=18, help="BCM GPIO pin for Gripper Servo (default: 18 / Physical Pin 12)")
    parser.add_argument("--port", type=int, default=4210, help="UDP command port (default: 4210)")
    args = parser.parse_args()

    node = SwarmNode(node_id=args.id, udp_port=args.port)

    # Declare attached hardware ONLY — Zero Control Logic!
    node.register_custom_actuator("servo", _make_ubuntu24_servo_driver(args.servo_pin))
    node.register_cpu_temp("cpu_temp")             # RPi CPU temperature (C)
    node.register_system_load("sys_load")          # RPi [1m_load, ram_%]
    node.register_wifi_rssi("rssi")                # Wi-Fi signal strength (dBm)

    node.start(block=True)


if __name__ == "__main__":
    main()
