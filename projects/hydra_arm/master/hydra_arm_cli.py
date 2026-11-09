#!/usr/bin/env python3
"""
===============================================================================
OpenSwarm HydraArm CLI — Interactive Terminal Controller for the 4-Node Arm
===============================================================================
Allows typing joint angles directly in the terminal on your Linux Master PC:
  hydra> base 120          # Rotate ESP32 Base Yaw to 120 deg
  hydra> shoulder 110      # Tilt Arduino UNO Q Shoulder Pitch to 110 deg
  hydra> elbow 75          # Move RP2040 Elbow Pitch to 75 deg
  hydra> gripper 20        # Open Raspberry Pi Gripper Claw to 20 deg
  hydra> pose 90 120 70 85 # Command all 4 controllers at once!
  hydra> home              # Return all 4 joints to [90, 90, 90, 45]
  hydra> demo              # Run a coordinated 4-controller pick & place wave
  hydra> status            # Print live 20 Hz telemetry from all 4 controllers
===============================================================================
"""

import argparse
import os
import sys
import time
from typing import Dict, Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MASTER_PKG_DIR = os.path.join(REPO_ROOT, "master")
if MASTER_PKG_DIR not in sys.path:
    sys.path.insert(0, MASTER_PKG_DIR)

from openswarm.master import SwarmMaster

JOINTS = {
    "base":     {"node_id": "arm_base_esp32",    "ctrl": "ESP32 (GPIO 13)",             "min": 0,  "max": 180, "home": 90},
    "shoulder": {"node_id": "arm_shoulder_unoq", "ctrl": "Arduino UNO Q (Pin D9)",      "min": 20, "max": 160, "home": 140},
    "elbow":    {"node_id": "arm_elbow_rp2040",  "ctrl": "RP2040 (Pin D6 / GP6)",       "min": 20, "max": 160, "home": 90},
    "gripper":  {"node_id": "arm_gripper_rpi",   "ctrl": "Raspberry Pi (BCM GPIO 18)",  "min": 10, "max": 95,  "home": 45},
}

ALIASES = {
    "b": "base", "j1": "base", "1": "base",
    "s": "shoulder", "j2": "shoulder", "2": "shoulder",
    "e": "elbow", "j3": "elbow", "3": "elbow",
    "g": "gripper", "j4": "gripper", "4": "gripper",
}


class HydraArmCLI:
    def __init__(self, ip_overrides: Dict[str, Optional[str]]):
        self.master = SwarmMaster()
        self.angles = {k: v["home"] for k, v in JOINTS.items()}

        for jname, ip in ip_overrides.items():
            if ip and jname in JOINTS:
                self.master.connect(JOINTS[jname]["node_id"], ip=ip)

    def set_joint(self, joint: str, angle: int) -> None:
        cfg = JOINTS[joint]
        clamped = max(cfg["min"], min(cfg["max"], int(angle)))
        self.angles[joint] = clamped
        node = self.master.get(cfg["node_id"])
        if node is not None:
            node.servo("servo", clamped)
            print(f"  [SENT -> {cfg['node_id']} ({node.ip}:{node.port})] {joint.upper()} = {clamped}°")
        else:
            print(f"  [QUEUED (Node '{cfg['node_id']}' not discovered yet)] {joint.upper()} = {clamped}°")

    def set_pose(self, b: int, s: int, e: int, g: int) -> None:
        self.set_joint("base", b)
        self.set_joint("shoulder", s)
        self.set_joint("elbow", e)
        self.set_joint("gripper", g)

    def print_status(self) -> None:
        print("\n" + "-" * 78)
        print(f" {'JOINT':<10} | {'NODE ID':<20} | {'CONTROLLER':<26} | {'ANGLE':<6} | {'STATUS / TELEMETRY'}")
        print("-" * 78)
        for jname, cfg in JOINTS.items():
            node = self.master.get(cfg["node_id"])
            ang = f"{self.angles[jname]}°"
            if node and node.is_online:
                state_str = f"ONLINE ({node.ip}) {node.sensors}"
            else:
                state_str = "WAITING FOR HELLO..."
            print(f" {jname:<10} | {cfg['node_id']:<20} | {cfg['ctrl']:<26} | {ang:<6} | {state_str}")
        print("-" * 78 + "\n")

    def run_demo_wave(self) -> None:
        print("Running coordinated 4-controller pick-and-place sequence...")
        waypoints = [
            ("Home Pose",        (90,  90,  90, 25)),
            ("Reach Object",     (90, 125,  65, 25)),
            ("Close Gripper",    (90, 125,  65, 85)),
            ("Lift Object",      (90,  75, 110, 85)),
            ("Swing Left",       (135, 75, 110, 85)),
            ("Place Left",       (135, 120, 70, 85)),
            ("Release Gripper",  (135, 120, 70, 25)),
            ("Return Home",      (90,  90,  90, 45)),
        ]
        for label, (b, s, e, g) in waypoints:
            print(f"\n-> Step: {label} {b, s, e, g}")
            self.set_pose(b, s, e, g)
            time.sleep(1.1)

    def repl(self) -> None:
        print("=" * 78)
        print("  OpenSwarm HydraArm — Interactive Terminal Controller")
        print("=" * 78)
        print("  Scanning for the 4 arm Slave nodes on Wi-Fi (2.0s)...")
        time.sleep(2.0)
        self.print_status()
        print("Commands:")
        print("  base <0..180>              (or: b 120)")
        print("  shoulder <20..160>         (or: s 110)")
        print("  elbow <20..160>            (or: e 75)")
        print("  gripper <10..95>           (or: g 85)")
        print("  pose <base> <sh> <el> <gr> (e.g.: pose 90 120 70 45)")
        print("  connect <joint> <ip>       (e.g.: connect gripper 192.168.0.150)")
        print("  home | demo | status | quit\n")

        try:
            while True:
                raw = input("hydra> ").strip()
                if not raw:
                    continue
                parts = raw.split()
                cmd = parts[0].lower()

                if cmd in ("quit", "exit", "q"):
                    break
                elif cmd == "status":
                    self.print_status()
                elif cmd == "home":
                    self.set_pose(90, 140, 90, 45)
                elif cmd == "demo":
                    self.run_demo_wave()
                elif cmd == "pose" and len(parts) == 5:
                    self.set_pose(int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]))
                elif cmd == "connect" and len(parts) == 3:
                    j = ALIASES.get(parts[1].lower(), parts[1].lower())
                    if j in JOINTS:
                        node = self.master.connect(JOINTS[j]["node_id"], ip=parts[2])
                        print(f"Connected '{node.node_id}' at {node.ip}:{node.port}")
                    else:
                        print("Unknown joint. Use: base, shoulder, elbow, or gripper.")
                else:
                    j = ALIASES.get(cmd, cmd)
                    if j in JOINTS and len(parts) == 2:
                        self.set_joint(j, int(parts[1]))
                    else:
                        print("Unrecognized command. Try `base 120`, `pose 90 110 80 45`, `status`, or `home`.")
        except (KeyboardInterrupt, EOFError):
            print("\nShutting down HydraArm Master...")
        finally:
            self.master.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenSwarm HydraArm Terminal Controller")
    parser.add_argument("--base-ip", type=str, default=None, help="Optional direct IP for arm_base_esp32")
    parser.add_argument("--shoulder-ip", type=str, default=None, help="Optional direct IP for arm_shoulder_unoq")
    parser.add_argument("--elbow-ip", type=str, default=None, help="Optional direct IP for arm_elbow_rp2040")
    parser.add_argument("--gripper-ip", type=str, default=None, help="Optional direct IP for arm_gripper_rpi")
    args = parser.parse_args()

    cli = HydraArmCLI({
        "base": args.base_ip,
        "shoulder": args.shoulder_ip,
        "elbow": args.elbow_ip,
        "gripper": args.gripper_ip,
    })
    cli.repl()


if __name__ == "__main__":
    main()
