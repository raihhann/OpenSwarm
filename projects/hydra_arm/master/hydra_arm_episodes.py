#!/usr/bin/env python3
"""
===============================================================================
OpenSwarm HydraArm — Episode Player & Manager (`hydra_arm_episodes.py`)
===============================================================================
Plays back recorded movement episodes saved by HydraArm Studio (`projects/hydra_arm/episodes/*.json`)
using the same silky-smooth degree-by-degree motion across your ESP32, RP2040,
and Raspberry Pi Slave controllers!

Usage Examples:
  # 1. List all saved episodes in projects/hydra_arm/episodes/:
  python3 projects/hydra_arm/master/hydra_arm_episodes.py --list

  # 2. Play an episode once:
  python3 projects/hydra_arm/master/hydra_arm_episodes.py --play episode_1.json

  # 3. Play an episode in an infinite loop (great for live demos!):
  python3 projects/hydra_arm/master/hydra_arm_episodes.py --play episode_1.json --loop
===============================================================================
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, Any, Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MASTER_PKG_DIR = os.path.join(REPO_ROOT, "master")
EPISODES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "episodes"))
if MASTER_PKG_DIR not in sys.path:
    sys.path.insert(0, MASTER_PKG_DIR)

from openswarm.master import SwarmMaster

JOINTS = {
    "base":     {"node_id": "arm_base_esp32",   "act": "servo",          "home": 90},
    "shoulder": {"node_id": "arm_gripper_rpi",  "act": "shoulder_servo", "home": 140},
    "elbow":    {"node_id": "arm_elbow_rp2040", "act": "servo",          "home": 90},
    "gripper":  {"node_id": "arm_gripper_rpi",  "act": "gripper_servo",  "home": 45},
}


class EpisodePlayer:
    def __init__(self, step_delay_ms: int = 12):
        self.master = SwarmMaster()
        self.step_delay_sec = max(0.004, step_delay_ms / 1000.0)
        self.current_angles: Dict[str, int] = {k: v["home"] for k, v in JOINTS.items()}

    def step_smoothly_to_pose(self, target_pose: Dict[str, int]) -> None:
        """Steps all 4 joints smoothly 1–2 degrees at a time toward `target_pose`."""
        while any(self.current_angles[k] != int(target_pose.get(k, self.current_angles[k])) for k in JOINTS):
            for k, cfg in JOINTS.items():
                curr = self.current_angles[k]
                tgt = int(target_pose.get(k, curr))
                if curr != tgt:
                    diff = tgt - curr
                    step = 2 if abs(diff) > 15 else 1
                    nxt = curr + (step if diff > 0 else -step)
                    self.current_angles[k] = nxt
                    node = self.master.get(cfg["node_id"])
                    if node is not None:
                        node.servo(cfg["act"], nxt)
            time.sleep(self.step_delay_sec)

    def send_pose_direct(self, target_pose: Dict[str, int]) -> None:
        """Sends an immediate pose frame during high-frequency trajectory playback."""
        for k, cfg in JOINTS.items():
            if k in target_pose:
                ang = int(target_pose[k])
                if self.current_angles.get(k) != ang:
                    self.current_angles[k] = ang
                    node = self.master.get(cfg["node_id"])
                    if node is not None:
                        node.servo(cfg["act"], ang)

    def play_file(self, filename: str, loop: bool = False, speed: float = 1.0) -> None:
        fpath = filename if os.path.isfile(filename) else os.path.join(EPISODES_DIR, filename)
        if not fpath.endswith(".json") and not os.path.isfile(fpath):
            fpath += ".json"
        if not os.path.isfile(fpath):
            print(f"[Error] Episode file not found: {fpath}")
            return

        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)

        frames = data.get("frames", [])
        if not frames:
            print(f"[Error] Episode '{fpath}' has no frames.")
            return

        print("=" * 74)
        print(f"  OpenSwarm HydraArm — Episode Player")
        print(f"  Episode File : {os.path.basename(fpath)} ({len(frames)} steps, {data.get('duration_sec', 0)}s)")
        print("  Waiting 2.0s to discover ESP32, RP2040, and Raspberry Pi on Wi-Fi...")
        print("=" * 74)
        time.sleep(2.0)

        try:
            iteration = 1
            while True:
                print(f"\n▶ Playing '{data.get('name', os.path.basename(fpath))}' (Run #{iteration})...")
                # Smoothly glide to the starting pose of the episode first
                first_pose = frames[0].get("joints", {})
                self.step_smoothly_to_pose(first_pose)

                start_t = time.monotonic()
                for idx, frame in enumerate(frames):
                    target_t = float(frame.get("t", 0.0)) / max(0.1, speed)
                    wait_s = target_t - (time.monotonic() - start_t)
                    if wait_s > 0:
                        time.sleep(wait_s)
                    pose = frame.get("joints", {})
                    self.step_smoothly_to_pose(pose)
                    print(
                        f"  [{idx + 1:3d}/{len(frames):3d} | t={target_t:5.2f}s] "
                        f"Base={pose.get('base')}° Shoulder={pose.get('shoulder')}° "
                        f"Elbow={pose.get('elbow')}° Gripper={pose.get('gripper')}°"
                    )

                if not loop:
                    print("\n[DONE] Episode playback finished.")
                    break
                iteration += 1
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n[STOPPED] Playback interrupted by user.")
        finally:
            self.master.close()


def list_saved_episodes() -> None:
    os.makedirs(EPISODES_DIR, exist_ok=True)
    files = sorted(fn for fn in os.listdir(EPISODES_DIR) if fn.endswith(".json"))
    print("=" * 74)
    print(f"  Saved HydraArm Episodes in: {EPISODES_DIR}")
    print("=" * 74)
    if not files:
        print("  (No episodes recorded yet. Use the '● Record' button in HydraArm Studio!)")
        return
    for fn in files:
        fpath = os.path.join(EPISODES_DIR, fn)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                d = json.load(f)
            print(
                f"  - {fn:<26} | {d.get('steps', 0):4d} steps | "
                f"{d.get('duration_sec', 0):5.1f}s | Created: {d.get('created_at', '--')}"
            )
        except Exception:
            print(f"  - {fn}")


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenSwarm HydraArm Episode Player")
    parser.add_argument("--list", action="store_true", help="List all recorded episodes")
    parser.add_argument("--play", type=str, default=None, help="Episode filename to play (e.g. episode_1.json)")
    parser.add_argument("--loop", action="store_true", help="Loop the episode continuously")
    parser.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier (default: 1.0)")
    args = parser.parse_args()

    if args.list or not args.play:
        list_saved_episodes()
        if not args.play:
            return

    player = EpisodePlayer()
    player.play_file(args.play, loop=args.loop, speed=args.speed)


if __name__ == "__main__":
    main()
