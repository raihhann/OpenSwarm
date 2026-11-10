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
import math
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

from hydra_arm_model import JOINTS, validate_episode, step_toward



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
                    node = self.master.subscribe(cfg["node_id"])
                    if node is None or not node.is_online:
                        raise ConnectionError("Joint controller is offline: " + k)
                    node.servo(cfg["act"], nxt)
                    self.current_angles[k] = nxt
            time.sleep(self.step_delay_sec)

    def send_pose_direct(self, target_pose: Dict[str, int]) -> None:
        """Sends an immediate pose frame during high-frequency trajectory playback."""
        for k, cfg in JOINTS.items():
            if k in target_pose:
                ang = int(target_pose[k])
                node = self.master.subscribe(cfg["node_id"])
                if node is None or not node.is_online:
                    raise ConnectionError("Joint controller is offline: " + k)
                node.servo(cfg["act"], ang)
                self.current_angles[k] = ang

    def play_file(self, filename: str, loop: bool = False, speed: float = 1.0) -> None:
        try:
            self._play_file(filename, loop, speed)
        finally:
            self.master.close()

    def _play_file(self, filename: str, loop: bool, speed: float) -> None:
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError("Playback speed must be finite and positive")
        fpath = filename if os.path.isfile(filename) else os.path.join(EPISODES_DIR, filename)
        if not fpath.endswith(".json") and not os.path.isfile(fpath):
            fpath += ".json"
        if not os.path.isfile(fpath):
            print(f"[Error] Episode file not found: {fpath}")
            return

        with open(fpath, "r", encoding="utf-8") as f:
            data = validate_episode(json.load(f))

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
                print(f"\n[PLAY] Playing '{data.get('name', os.path.basename(fpath))}' (Run #{iteration})...")
                start_t = time.monotonic()
                targets = dict(self.current_angles)
                pending = set()
                idx = 0
                # Target changes follow the same clock as Studio; interpolation
                # runs between frames instead of delaying subsequent timestamps.
                while True:
                    elapsed = time.monotonic() - start_t
                    while idx < len(frames) and frames[idx]["t"] / speed <= elapsed:
                        targets.update(frames[idx]["joints"])
                        pending.update(frames[idx]["joints"])
                        idx += 1
                    for joint, cfg in JOINTS.items():
                        if joint not in pending:
                            continue
                        node = self.master.subscribe(cfg["node_id"])
                        if node is None or not node.is_online:
                            raise ConnectionError("Joint controller is offline: " + joint)
                        angle = step_toward(self.current_angles[joint], targets[joint])
                        node.servo(cfg["act"], angle)
                        self.current_angles[joint] = angle
                        if angle == targets[joint]:
                            pending.discard(joint)
                    if idx == len(frames) and elapsed >= data["duration_sec"] / speed and self.current_angles == targets:
                        break
                    time.sleep(self.step_delay_sec)

                if not loop:
                    print("\n[DONE] Episode playback finished.")
                    break
                iteration += 1
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n[STOPPED] Playback interrupted by user.")


def list_saved_episodes() -> None:
    os.makedirs(EPISODES_DIR, exist_ok=True)
    files = sorted(fn for fn in os.listdir(EPISODES_DIR) if fn.endswith(".json"))
    print("=" * 74)
    print(f"  Saved HydraArm Episodes in: {EPISODES_DIR}")
    print("=" * 74)
    if not files:
        print("  (No episodes recorded yet. Use the 'Record' button in HydraArm Studio!)")
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
