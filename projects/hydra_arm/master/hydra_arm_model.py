"""Shared HydraArm joint configuration and episode validation."""

import math
from typing import Dict, Any


def controller_addresses(overrides):
    """Resolve shared-controller joint aliases once, rejecting contradictory IPs."""
    addresses = {}
    for joint, address in (overrides or {}).items():
        if not address:
            continue
        if joint not in JOINT_CONFIG:
            raise ValueError("Unknown joint: %s" % joint)
        node_id = JOINT_CONFIG[joint]["node_id"]
        if node_id in addresses and addresses[node_id] != address:
            raise ValueError("Conflicting addresses for shared controller: %s" % node_id)
        addresses[node_id] = address
    return addresses


def step_toward(current, target):
    distance = target - current
    step = min(abs(distance), 2 if abs(distance) > 15 else 1)
    return current + (step if distance > 0 else -step)


def validate_episode(data):
    """Normalize a complete episode before any movement is dispatched.

    Frames describe target changes, not measured positions. Partial poses hold
    omitted joints; timestamps are monotonic and duration includes final dwell.
    """
    if not isinstance(data, dict) or not isinstance(data.get("frames"), list) or not data["frames"]:
        raise ValueError("Episode must contain at least one frame")
    frames, previous = [], 0.0
    for frame in data["frames"]:
        if not isinstance(frame, dict):
            raise ValueError("Frame must be an object")
        timestamp = frame.get("t", 0)
        if (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
                or not math.isfinite(timestamp) or timestamp < previous):
            raise ValueError("Frame times must be finite, nonnegative and ordered")
        pose = frame.get("joints")
        if not isinstance(pose, dict) or not pose:
            raise ValueError("Frame must contain joint targets")
        normalized = {}
        for joint, angle in pose.items():
            if joint not in JOINT_CONFIG:
                raise ValueError("Unknown joint: %s" % joint)
            cfg = JOINT_CONFIG[joint]
            if (isinstance(angle, bool) or not isinstance(angle, (int, float))
                    or not math.isfinite(angle) or int(angle) != angle
                    or not cfg["min_angle"] <= angle <= cfg["max_angle"]):
                raise ValueError("Joint angle outside configured limits: %s" % joint)
            normalized[joint] = int(angle)
        frames.append({"t": float(timestamp), "joints": normalized})
        previous = timestamp
    duration = data.get("duration_sec", previous)
    if (isinstance(duration, bool) or not isinstance(duration, (int, float))
            or not math.isfinite(duration) or duration < previous):
        raise ValueError("Duration must include the last frame")
    return {**data, "frames": frames, "steps": len(frames), "duration_sec": float(duration)}

JOINT_CONFIG: Dict[str, Dict[str, Any]] = {
    "base": {
        "joint_id": "base",
        "code": "J1",
        "label": "Base Yaw",
        "node_id": "arm_base_esp32",
        "actuator_name": "servo",
        "controller": "ESP32",
        "pin_label": "GPIO 13",
        "color": "#2563eb",
        "min_angle": 0,
        "max_angle": 180,
        "home_angle": 90,
        "angle": 90,
        "description": "Rotates the upper arm assembly left/right on the circular base.",
    },
    "shoulder": {
        "joint_id": "shoulder",
        "code": "J2",
        "label": "Shoulder Pitch",
        "node_id": "arm_shoulder_gripper_rpi",
        "actuator_name": "shoulder_servo",
        "controller": "Raspberry Pi",
        "pin_label": "BCM 14 (Pin 8)",
        "color": "#0284c7",
        "min_angle": 20,
        "max_angle": 160,
        "home_angle": 140,
        "angle": 140,
        "description": "Drives the twin vertical linkage bars forward and backward.",
    },
    "elbow": {
        "joint_id": "elbow",
        "code": "J3",
        "label": "Elbow Pitch",
        "node_id": "arm_elbow_rp2040",
        "actuator_name": "servo",
        "controller": "RP2040",
        "pin_label": "GP6 (Pin D6)",
        "color": "#4f46e5",
        "min_angle": 20,
        "max_angle": 160,
        "home_angle": 90,
        "angle": 90,
        "description": "Raises and lowers the grey skeletal forearm link.",
    },
    "gripper": {
        "joint_id": "gripper",
        "code": "J4",
        "label": "Gripper Claw",
        "node_id": "arm_shoulder_gripper_rpi",
        "actuator_name": "gripper_servo",
        "controller": "Raspberry Pi",
        "pin_label": "BCM 18 (Pin 12)",
        "color": "#0d9488",
        "min_angle": 10,
        "max_angle": 95,
        "home_angle": 45,
        "angle": 45,
        "description": "Opens (10°) and closes (95°) the geared parallel gripper fingers.",
    },
}


JOINTS = {k: {"node_id": v["node_id"], "act": v["actuator_name"],
              "ctrl": f'{v["controller"]} ({v["pin_label"]})',
              "min": v["min_angle"], "max": v["max_angle"], "home": v["home_angle"]}
          for k, v in JOINT_CONFIG.items()}
