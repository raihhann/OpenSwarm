#!/usr/bin/env python3
"""
===============================================================================
OpenSwarm HydraArm — Joint 2: SHOULDER PITCH Slave Node (Arduino UNO Q Linux MPU)
===============================================================================
Target Board : Arduino UNO Q (Qualcomm DragonWing QRB2210 Debian Linux side)
Node ID      : "arm_shoulder_unoq"
Joint Role   : Lower Shoulder Linkage Pitch (20..160 deg, Home = 90 deg)
Servo Pin    : UNO Q Digital Pin 9 (D9 — driven by the STM32U585 MCU via Bridge)

WIRING (Shoulder SG90 / MG90S Servo -> Arduino UNO Q Header):
  - Servo Orange/Yellow (Signal) -> Digital Pin 9 (D9)
  - Servo Red           (VCC 5V) -> 5V Power Supply / 5V Pin
  - Servo Brown/Black   (GND)    -> GND (MUST share common GND!)

HOW TO RUN ON ARDUINO UNO Q:
  1. Upload `unoq_mcu_bridge/unoq_mcu_bridge.ino` to the UNO Q's MCU (attaches Servo on Pin 9).
  2. On the UNO Q Linux terminal (SSH or App Lab terminal), run:
       python3 unoq_shoulder_node.py
===============================================================================
"""

import argparse
import os
import sys

# Ensure local `slaves/linux` package in the cloned repo is always importable
REPO_LINUX_SLAVE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "slaves", "linux"))
if os.path.isdir(REPO_LINUX_SLAVE) and REPO_LINUX_SLAVE not in sys.path:
    sys.path.insert(0, REPO_LINUX_SLAVE)

from openswarm_slave import SwarmNode


def _make_unoq_servo_driver(pin: int, default_angle: int = 140):
    """
    Forwards servo angle commands from the UNO Q Linux processor to the
    UNO Q STM32U585 microcontroller over Arduino's RPC Bridge (`set_servo`).
    """
    state = {"bridge": None}
    try:
        from arduino.app_utils import Bridge  # type: ignore

        state["bridge"] = Bridge
        print(f"[UNO Q Servo HAL] Connected to Arduino_RouterBridge -> MCU Pin D{pin}")
        try:
            Bridge.call("set_servo", int(default_angle))
            print(f"[UNO Q Servo HAL] Initialized Shoulder Servo D{pin} to default {default_angle} deg")
        except Exception as init_err:
            print(f"[UNO Q Servo HAL] Initial set_servo({default_angle}) warning: {init_err}")
    except Exception as exc:
        print(f"[UNO Q Servo HAL] arduino.app_utils.Bridge not detected ({exc}) — using LinuxHAL fallback")

    def write_servo(v1: int, _v2: int, _data: str) -> None:
        angle = max(0, min(180, int(v1)))
        if state["bridge"] is not None:
            try:
                state["bridge"].call("set_servo", int(angle))
            except Exception as err:
                print(f"  [UNO Q Bridge Warning] call('set_servo', {angle}) failed: {err}")
        print(f"  [UNO Q Shoulder Servo D{pin}] -> {angle:3d} deg")

    return write_servo


def main() -> None:
    parser = argparse.ArgumentParser(description="HydraArm Joint 2 — Arduino UNO Q Shoulder Slave Node")
    parser.add_argument("--id", type=str, default="arm_shoulder_unoq", help="Unique Slave Node ID")
    parser.add_argument("--servo-pin", type=int, default=9, help="UNO Q Digital PWM Pin (default: D9)")
    parser.add_argument("--port", type=int, default=4210, help="UDP command port (default: 4210)")
    args = parser.parse_args()

    node = SwarmNode(node_id=args.id, udp_port=args.port)

    # Declare attached hardware ONLY — Zero Control Logic!
    node.register_custom_actuator("servo", _make_unoq_servo_driver(args.servo_pin))
    node.register_cpu_temp("cpu_temp")             # UNO Q QRB2210 CPU temperature (C)
    node.register_system_load("sys_load")          # UNO Q [1m_load, ram_%]
    node.register_wifi_rssi("rssi")                # UNO Q Wi-Fi signal strength (dBm)

    node.start(block=True)


if __name__ == "__main__":
    main()
