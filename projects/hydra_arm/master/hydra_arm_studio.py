#!/usr/bin/env python3
"""
===============================================================================
OpenSwarm HydraArm Studio — 3D Interactive Digital Twin & Multi-Controller Master
===============================================================================
Controls the 4-DOF "Servo Mini Arm" where each servo is wired to a different
heterogeneous Slave controller over Wi-Fi UDP:
  - Joint 1 (Base Yaw)       -> ESP32             (node_id: "arm_base_esp32",           actuator: "servo")
  - Joint 2 (Shoulder Pitch) -> Raspberry Pi      (node_id: "arm_shoulder_gripper_rpi", actuator: "shoulder_servo")
  - Joint 3 (Elbow Pitch)    -> RP2040            (node_id: "arm_elbow_rp2040",         actuator: "servo")
  - Joint 4 (Gripper Claw)   -> Raspberry Pi      (node_id: "arm_shoulder_gripper_rpi", actuator: "gripper_servo")

Features:
  - Interactive 3D Three.js replica of the "Servo Mini Arm by Luca Dilo"
  - Click ANY of the 4 servo motors directly on the 3D arm -> an interactive
    angle slider pops up over that joint!
  - Moving the slider moves both the 3D arm AND the physical servo in real time
    over OpenSwarm UDP (Port 4210 / 4211).
  - Live per-controller connection status, IP display, manual IP connect, and
    20 Hz telemetry readout (Wi-Fi RSSI, RP2040 IMU, RPi CPU Temp).
===============================================================================
"""

import argparse
import asyncio
import json
import logging
import math
import os
import sys
import time
import tempfile
from datetime import datetime
from typing import Dict, Any, List, Optional

from aiohttp import web

# Ensure local `master/` package is importable even if not pip-installed yet
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MASTER_PKG_DIR = os.path.join(REPO_ROOT, "master")
EPISODES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "episodes"))
if MASTER_PKG_DIR not in sys.path:
    sys.path.insert(0, MASTER_PKG_DIR)

from openswarm.master import SwarmMaster

logger = logging.getLogger("hydra_arm_studio")


from hydra_arm_model import JOINT_CONFIG, validate_episode, step_toward, controller_addresses


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>OpenSwarm — HydraArm Teach Pendant</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<style>
  :root {
    --bg-app: #f4f5f7;
    --bg-panel: #ffffff;
    --bg-subtle: #f8f9fa;
    --bg-muted: #f1f3f5;
    --border: #e4e4e7;
    --border-strong: #d4d4d8;
    --text-primary: #18181b;
    --text-secondary: #52525b;
    --text-muted: #71717a;
    --accent: #18181b;
    --accent-blue: #2563eb;
    --accent-blue-soft: #eff6ff;
    --green: #16a34a;
    --green-bg: #f0fdf4;
    --green-border: #bbf7d0;
    --amber: #d97706;
    --amber-bg: #fffbeb;
    --amber-border: #fde68a;
    --red: #dc2626;
    --red-bg: #fef2f2;
    --red-border: #fecaca;
    --mono: 'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    --sans: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
  body {
    background: var(--bg-app);
    color: var(--text-primary);
    font-family: var(--sans);
    overflow: hidden;
    height: 100vh;
    width: 100vw;
    display: flex;
    flex-direction: column;
    -webkit-font-smoothing: antialiased;
  }

  /* Top Docked Header Bar */
  .topbar {
    height: 52px;
    background: var(--bg-panel);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 18px;
    z-index: 20;
    flex-shrink: 0;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .brand-mark {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--bg-panel);
    background: var(--text-primary);
    padding: 4px 8px;
    border-radius: 4px;
  }
  .brand-divider {
    width: 1px;
    height: 18px;
    background: var(--border);
  }
  .brand-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    letter-spacing: -0.01em;
  }
  .brand-sub {
    font-size: 12px;
    color: var(--text-muted);
    font-family: var(--mono);
  }

  .top-actions {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .preset-group {
    display: flex;
    align-items: center;
    background: var(--bg-muted);
    padding: 3px;
    border-radius: 6px;
    border: 1px solid var(--border);
    gap: 2px;
  }
  .preset-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    padding: 0 8px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .btn {
    background: var(--bg-panel);
    color: var(--text-primary);
    border: 1px solid var(--border);
    padding: 5px 11px;
    border-radius: 5px;
    font-size: 12px;
    font-weight: 500;
    font-family: var(--sans);
    cursor: pointer;
    transition: background 0.1s ease, border-color 0.1s ease;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
  }
  .btn:hover {
    background: var(--bg-subtle);
    border-color: var(--border-strong);
  }
  .btn:active {
    background: var(--bg-muted);
  }
  .preset-group .btn {
    border-color: transparent;
    background: transparent;
    color: var(--text-secondary);
    padding: 4px 10px;
  }
  .preset-group .btn:hover {
    background: var(--bg-panel);
    color: var(--text-primary);
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
  }
  .btn-dark {
    background: var(--text-primary);
    color: #ffffff;
    border-color: var(--text-primary);
  }
  .btn-dark:hover {
    background: #27272a;
    border-color: #27272a;
  }

  /* Main Workspace Split: Left Inspector + Right 3D Viewport */
  .workspace {
    flex: 1;
    display: flex;
    position: relative;
    overflow: hidden;
  }

  /* Left Docked Inspector */
  .sidebar {
    width: 372px;
    background: var(--bg-panel);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    z-index: 15;
    flex-shrink: 0;
  }
  .sidebar-scroll {
    flex: 1;
    overflow-y: auto;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 2px 4px 2px;
  }
  .section-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
  }
  .section-meta {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-muted);
  }

  /* Joint Axis Cards */
  .joint-card {
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 7px;
    padding: 11px 12px;
    transition: border-color 0.12s ease, box-shadow 0.12s ease;
    cursor: pointer;
  }
  .joint-card:hover {
    border-color: var(--border-strong);
  }
  .joint-card.active {
    border-color: var(--accent-blue);
    box-shadow: 0 0 0 1px var(--accent-blue);
    background: #fcfdff;
  }
  .joint-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .joint-id-group {
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .axis-badge {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    background: var(--bg-muted);
    color: var(--text-primary);
    border: 1px solid var(--border);
  }
  .joint-card.active .axis-badge {
    background: var(--accent-blue);
    color: #ffffff;
    border-color: var(--accent-blue);
  }
  .joint-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
  }
  .status-pill {
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 4px;
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    display: inline-block;
  }
  .status-online {
    background: var(--green-bg);
    color: var(--green);
    border: 1px solid var(--green-border);
  }
  .status-online .status-dot {
    background: var(--green);
  }
  .status-waiting {
    background: var(--bg-muted);
    color: var(--text-muted);
    border: 1px solid var(--border);
  }
  .status-waiting .status-dot {
    background: #a1a1aa;
  }

  .joint-hw-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-muted);
    margin-bottom: 9px;
  }
  .hw-tag {
    background: var(--bg-subtle);
    padding: 1px 6px;
    border-radius: 3px;
    border: 1px solid var(--border);
    color: var(--text-secondary);
  }

  /* Precision Control Row: [-1] [Slider] [+1] [Angle] */
  .control-row {
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .jog-btn {
    width: 24px;
    height: 24px;
    border-radius: 4px;
    border: 1px solid var(--border);
    background: var(--bg-subtle);
    color: var(--text-secondary);
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .jog-btn:hover {
    background: var(--bg-muted);
    color: var(--text-primary);
    border-color: var(--border-strong);
  }
  .slider-wrap {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  input[type="range"].axis-slider {
    -webkit-appearance: none;
    appearance: none;
    width: 100%;
    height: 5px;
    background: #e4e4e7;
    border-radius: 999px;
    outline: none;
    cursor: pointer;
  }
  input[type="range"].axis-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--text-primary);
    border: 2px solid #ffffff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    cursor: grab;
  }
  .joint-card.active input[type="range"].axis-slider::-webkit-slider-thumb {
    background: var(--accent-blue);
  }
  .range-limits {
    display: flex;
    justify-content: space-between;
    font-family: var(--mono);
    font-size: 9.5px;
    color: #a1a1aa;
  }
  .readout-box {
    min-width: 58px;
    text-align: right;
    font-family: var(--mono);
    background: var(--bg-subtle);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 3px 6px;
  }
  .angle-val {
    font-size: 13px;
    font-weight: 700;
    color: var(--text-primary);
    display: block;
    line-height: 1.1;
  }
  .pulse-val {
    font-size: 9.5px;
    color: var(--text-muted);
    display: block;
  }

  .telemetry-strip {
    margin-top: 7px;
    padding-top: 6px;
    border-top: 1px dashed var(--border);
    font-family: var(--mono);
    font-size: 10.5px;
    color: var(--text-secondary);
    display: none;
  }

  /* Bottom Docked Trajectory Recorder in Sidebar */
  .recorder-dock {
    padding: 12px 14px;
    background: var(--bg-subtle);
    border-top: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .rec-row {
    display: flex;
    gap: 6px;
  }
  .rec-input {
    flex: 1;
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 5px;
    color: var(--text-primary);
    padding: 5px 9px;
    font-size: 12px;
    font-family: var(--mono);
    outline: none;
  }
  .rec-input:focus {
    border-color: var(--text-primary);
  }
  .btn-rec {
    background: var(--bg-panel);
    border: 1px solid var(--red-border);
    color: var(--red);
    font-weight: 600;
  }
  .btn-rec:hover {
    background: var(--red-bg);
    border-color: var(--red);
  }
  .btn-rec.recording {
    background: var(--red);
    border-color: var(--red);
    color: #ffffff;
  }
  .btn-play {
    background: var(--bg-panel);
    border: 1px solid var(--green-border);
    color: var(--green);
    font-weight: 600;
  }
  .btn-play:hover {
    background: var(--green-bg);
    border-color: var(--green);
  }
  .btn-play.playing {
    background: var(--green);
    border-color: var(--green);
    color: #ffffff;
  }
  .rec-status {
    font-family: var(--mono);
    font-size: 11px;
    padding: 5px 8px;
    border-radius: 4px;
    background: var(--bg-panel);
    border: 1px solid var(--border);
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* Right 3D Viewport Area */
  .viewport {
    flex: 1;
    position: relative;
    background: var(--bg-app);
    overflow: hidden;
  }
  #canvas-container {
    position: absolute;
    inset: 0;
  }

  /* Viewport Corner HUD Overlay */
  .viewport-hud {
    position: absolute;
    bottom: 14px;
    left: 14px;
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 10px;
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-secondary);
    pointer-events: none;
    z-index: 10;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
  }

  /* 3D Servo Callout Tags in Viewport */
  .servo-tag {
    position: absolute;
    padding: 3px 8px;
    background: rgba(255, 255, 255, 0.94);
    border: 1px solid var(--border-strong);
    border-radius: 4px;
    color: var(--text-primary);
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 600;
    pointer-events: auto;
    cursor: pointer;
    transform: translate(-50%, -50%);
    white-space: nowrap;
    box-shadow: 0 2px 5px rgba(0,0,0,0.06);
    transition: border-color 0.1s ease, transform 0.1s ease;
    z-index: 12;
  }
  .servo-tag:hover {
    border-color: var(--text-primary);
    transform: translate(-50%, -50%) scale(1.04);
  }
  .servo-tag.active {
    background: var(--text-primary);
    color: #ffffff;
    border-color: var(--text-primary);
  }

  /* Floating 3D Popover Inspector */
  #floating-popup {
    position: absolute;
    width: 268px;
    background: #ffffff;
    border: 1px solid var(--border-strong);
    border-radius: 8px;
    padding: 12px 14px;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.12), 0 4px 10px -3px rgba(0, 0, 0, 0.06);
    z-index: 25;
    display: none;
    pointer-events: auto;
    transform: translate(-50%, -115%);
  }
  #floating-popup::after {
    content: "";
    position: absolute;
    bottom: -6px;
    left: 50%;
    transform: translateX(-50%) rotate(45deg);
    width: 10px;
    height: 10px;
    background: #ffffff;
    border-right: 1px solid var(--border-strong);
    border-bottom: 1px solid var(--border-strong);
  }
  .popup-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2px;
  }
  .popup-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
  }
  .popup-close {
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 14px;
    cursor: pointer;
    padding: 2px 4px;
    border-radius: 4px;
  }
  .popup-close:hover {
    background: var(--bg-muted);
    color: var(--text-primary);
  }
  .popup-sub {
    font-family: var(--mono);
    font-size: 10.5px;
    color: var(--text-muted);
    margin-bottom: 10px;
  }
  .popup-slider-wrap {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 10px;
  }
  .popup-slider-wrap input[type="range"] {
    flex: 1;
    cursor: pointer;
    accent-color: var(--text-primary);
  }
  .popup-angle-badge {
    font-family: var(--mono);
    font-size: 14px;
    font-weight: 700;
    color: var(--text-primary);
    min-width: 42px;
    text-align: right;
  }
  .popup-quick-btns {
    display: flex;
    justify-content: space-between;
    gap: 4px;
  }
  .popup-quick-btns button {
    flex: 1;
    background: var(--bg-subtle);
    border: 1px solid var(--border);
    color: var(--text-secondary);
    font-family: var(--mono);
    font-size: 10.5px;
    font-weight: 600;
    padding: 4px 0;
    border-radius: 4px;
    cursor: pointer;
  }
  .popup-quick-btns button:hover {
    background: var(--bg-muted);
    color: var(--text-primary);
    border-color: var(--border-strong);
  }
</style>
</head>
<body>

<!-- Top Docked Toolbar -->
<header class="topbar">
  <div class="brand">
    <span class="brand-mark">OPENSWARM</span>
    <span class="brand-divider"></span>
    <span class="brand-title">HydraArm Teach Pendant</span>
    <span class="brand-sub" id="nodes-summary-badge">UDP :4210 / :4211</span>
  </div>
  <div class="top-actions">
    <div class="preset-group">
      <span class="preset-label">Poses</span>
      <button class="btn" onclick="sendPreset(90, 140, 90, 45)">Home</button>
      <button class="btn" onclick="sendPreset(90, 125, 65, 20)">Reach</button>
      <button class="btn" onclick="sendPreset(90, 125, 65, 85)">Grasp</button>
      <button class="btn" onclick="sendPreset(135, 75, 115, 85)">Lift Left</button>
      <button class="btn" onclick="sendPreset(45, 115, 75, 20)">Place Right</button>
    </div>
    <button class="btn" onclick="resetCameraView()">Reset View</button>
  </div>
</header>

<div class="workspace">
  <!-- Left Docked Inspector -->
  <aside class="sidebar">
    <div class="sidebar-scroll">
      <div class="section-header">
        <span class="section-title">Joint Axes (4-DOF)</span>
        <span class="section-meta">50 Hz · 500–2400 µs</span>
      </div>
      <div id="joint-cards-container" style="display:flex; flex-direction:column; gap:8px;"></div>
    </div>

    <!-- Episode Recorder & Player -->
    <div class="recorder-dock">
      <div class="section-header" style="padding-bottom:2px;">
        <span class="section-title">Trajectory Recorder</span>
        <span class="section-meta" id="rec-step-badge">episodes/</span>
      </div>
      <div class="rec-row">
        <input type="text" id="episode-name-input" class="rec-input" placeholder="episode_name" value="episode_1" />
        <button class="btn btn-rec" id="btn-rec-toggle" onclick="toggleRecording()">Record</button>
      </div>
      <div class="rec-row">
        <select id="episode-select" class="rec-input"></select>
        <button class="btn btn-play" id="btn-play-ep" onclick="playSelectedEpisode(false)">Play</button>
        <button class="btn" id="btn-loop-ep" onclick="playSelectedEpisode(true)">Loop</button>
        <button class="btn" onclick="stopPlayback()">Stop</button>
      </div>
      <div class="rec-status" id="rec-status-box">Idle — Ready to record or replay</div>
    </div>
  </aside>

  <!-- Right 3D Viewport -->
  <main class="viewport" id="viewport-root">
    <div id="canvas-container"></div>

    <!-- Floating Popover over Selected 3D Servo -->
    <div id="floating-popup">
      <div class="popup-header">
        <div class="popup-title" id="popup-title">J1 · Base Yaw</div>
        <button class="popup-close" onclick="closePopup()">✕</button>
      </div>
      <div class="popup-sub" id="popup-sub">ESP32 (arm_base_esp32) · GPIO 13</div>
      <div class="popup-slider-wrap">
        <input type="range" id="popup-slider" min="0" max="180" value="90" />
        <div class="popup-angle-badge" id="popup-angle">90°</div>
      </div>
      <div class="popup-quick-btns">
        <button id="popup-btn-min">Min</button>
        <button id="popup-btn-m5">-5°</button>
        <button id="popup-btn-home">Home</button>
        <button id="popup-btn-p5">+5°</button>
        <button id="popup-btn-max">Max</button>
      </div>
    </div>

    <!-- 3D Clickable Callout Tags -->
    <div id="tags-layer"></div>

    <div class="viewport-hud">
      LMB: Orbit &nbsp;·&nbsp; RMB: Pan &nbsp;·&nbsp; Scroll: Zoom &nbsp;·&nbsp; Click Servo: Inspect Axis
    </div>
  </main>
</div>

<script>
const JOINTS_META = __JOINTS_META__;

function angleToPulseUs(deg) {
  return Math.round(500 + (deg / 180.0) * 1900);
}

let armState = Object.fromEntries(Object.entries(JOINTS_META).map(([id, meta]) => [id, meta.home]));
let targetAngles = { ...armState };
let selectedJoint = null;
let serverJointsData = {};

// ============================================================================
// WEBSOCKET CONNECTION TO LINUX MASTER
// ============================================================================
let ws = null;
function connectWS() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws`);
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.joints) {
      serverJointsData = msg.joints;
      for (const [jid, jinfo] of Object.entries(msg.joints)) {
        if (selectedJoint !== jid || (msg.recorder && msg.recorder.playing)) {
          targetAngles[jid] = jinfo.target_angle !== undefined ? jinfo.target_angle : jinfo.angle;
          updateCardReadout(jid, targetAngles[jid]);
        }
      }
      renderSidebarCards();
    }
    if (msg.recorder) {
      updateRecorderUI(msg.recorder);
    }
  };
  ws.onclose = () => setTimeout(connectWS, 1000);
}
connectWS();

function updateCardReadout(jointId, angle) {
  const sSlider = document.getElementById(`slider-${jointId}`);
  const sReadout = document.getElementById(`readout-${jointId}`);
  const sPulse = document.getElementById(`pulse-${jointId}`);
  if (sSlider) sSlider.value = angle;
  if (sReadout) sReadout.textContent = `${angle}°`;
  if (sPulse) sPulse.textContent = `${angleToPulseUs(angle)} µs`;
  const tag = tagElements[jointId];
  if (tag) {
    tag.textContent = `${JOINTS_META[jointId].code} · ${angle}°`;
  }
}

function sendJointAngle(jointId, angle) {
  const meta = JOINTS_META[jointId];
  const clamped = Math.max(meta.min, Math.min(meta.max, Math.round(angle)));
  targetAngles[jointId] = clamped;

  if (selectedJoint === jointId) {
    document.getElementById("popup-slider").value = clamped;
    document.getElementById("popup-angle").textContent = clamped + "°";
  }
  updateCardReadout(jointId, clamped);

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ op: "SET_JOINT", joint: jointId, angle: clamped }));
  }
}

function jogJoint(jointId, delta, ev) {
  if (ev) ev.stopPropagation();
  const cur = targetAngles[jointId] !== undefined ? targetAngles[jointId] : JOINTS_META[jointId].home;
  sendJointAngle(jointId, cur + delta);
}

function sendPreset(b, s, e, g) {
  sendJointAngle("base", b);
  sendJointAngle("shoulder", s);
  sendJointAngle("elbow", e);
  sendJointAngle("gripper", g);
}

let isRecordingState = false;
let lastEpisodeListJson = "";

function toggleRecording() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  if (!isRecordingState) {
    const epName = document.getElementById("episode-name-input").value.trim() || "episode";
    ws.send(JSON.stringify({ op: "START_RECORD", name: epName }));
  } else {
    ws.send(JSON.stringify({ op: "STOP_RECORD" }));
  }
}

function playSelectedEpisode(loopMode) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  const sel = document.getElementById("episode-select");
  if (!sel || !sel.value) return;
  ws.send(JSON.stringify({ op: "PLAY_EPISODE", filename: sel.value, loop: Boolean(loopMode) }));
}

function stopPlayback() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ op: "STOP_PLAYBACK" }));
}

function updateRecorderUI(rec) {
  isRecordingState = Boolean(rec.recording);
  const recBtn = document.getElementById("btn-rec-toggle");
  const playBtn = document.getElementById("btn-play-ep");
  const statusBox = document.getElementById("rec-status-box");

  if (rec.recording) {
    recBtn.className = "btn btn-rec recording";
    recBtn.textContent = "Save";
    statusBox.style.color = "var(--red)";
    statusBox.textContent = `REC ${rec.active_name} · ${rec.frame_count} frames (${rec.elapsed_sec}s)`;
  } else {
    recBtn.className = "btn btn-rec";
    recBtn.textContent = "Record";
    if (rec.playing) {
      playBtn.className = "btn btn-play playing";
      statusBox.style.color = "var(--green)";
      statusBox.textContent = `PLAY ${rec.playing_file} ${rec.loop ? "[LOOP]" : ""} · ${rec.play_progress}`;
    } else {
      playBtn.className = "btn btn-play";
      statusBox.style.color = "var(--text-secondary)";
      statusBox.textContent = rec.last_message || "Idle — Ready to record or replay";
    }
  }

  const listJson = JSON.stringify(rec.episodes || []);
  if (listJson !== lastEpisodeListJson) {
    lastEpisodeListJson = listJson;
    const sel = document.getElementById("episode-select");
    const prevVal = sel.value;
    sel.innerHTML = "";
    for (const ep of (rec.episodes || [])) {
      const opt = document.createElement("option");
      opt.value = ep.filename;
      opt.textContent = `${ep.filename} (${ep.steps}f, ${ep.duration_sec}s)`;
      sel.appendChild(opt);
    }
    if (rec.last_saved) {
      sel.value = rec.last_saved;
    } else if (prevVal) {
      sel.value = prevVal;
    }
  }
}

// ============================================================================
// SIDEBAR CARDS RENDERER
// ============================================================================
function buildSidebarCards() {
  const container = document.getElementById("joint-cards-container");
  container.innerHTML = "";
  for (const [jid, meta] of Object.entries(JOINTS_META)) {
    const initAng = targetAngles[jid];
    const card = document.createElement("div");
    card.className = "joint-card";
    card.id = `card-${jid}`;
    card.onclick = (ev) => {
      const tag = ev.target.tagName.toLowerCase();
      if (tag !== "input" && tag !== "button") {
        selectServoJoint(jid);
      }
    };
    card.innerHTML = `
      <div class="joint-top">
        <div class="joint-id-group">
          <span class="axis-badge">${meta.code}</span>
          <span class="joint-name">${meta.name}</span>
        </div>
        <span class="status-pill status-waiting" id="status-${jid}">
          <span class="status-dot"></span>
          <span id="status-text-${jid}">SIM</span>
        </span>
      </div>
      <div class="joint-hw-row">
        <span id="ctrl-${jid}">${meta.hw}</span>
        <span class="hw-tag" id="pin-${jid}">Home ${meta.home}°</span>
      </div>
      <div class="control-row">
        <button class="jog-btn" title="-1°" onclick="jogJoint('${jid}', -1, event)">-</button>
        <div class="slider-wrap">
          <input type="range" class="axis-slider" id="slider-${jid}"
                 min="${meta.min}" max="${meta.max}" value="${initAng}"
                 oninput="onSidebarSlider('${jid}', this.value)" />
          <div class="range-limits">
            <span>${meta.min}°</span>
            <span>${meta.home}°</span>
            <span>${meta.max}°</span>
          </div>
        </div>
        <button class="jog-btn" title="+1°" onclick="jogJoint('${jid}', 1, event)">+</button>
        <div class="readout-box">
          <span class="angle-val" id="readout-${jid}">${initAng}°</span>
          <span class="pulse-val" id="pulse-${jid}">${angleToPulseUs(initAng)} µs</span>
        </div>
      </div>
      <div class="telemetry-strip" id="telem-${jid}"></div>
    `;
    container.appendChild(card);
  }
}
buildSidebarCards();

function onSidebarSlider(jid, val) {
  selectServoJoint(jid);
  sendJointAngle(jid, parseInt(val, 10));
}

function renderSidebarCards() {
  let onlineCount = 0;
  const totalCount = Object.keys(JOINTS_META).length;

  for (const [jid, info] of Object.entries(serverJointsData)) {
    const pill = document.getElementById(`status-${jid}`);
    const statusText = document.getElementById(`status-text-${jid}`);
    const ctrl = document.getElementById(`ctrl-${jid}`);
    const pin = document.getElementById(`pin-${jid}`);
    const telem = document.getElementById(`telem-${jid}`);
    if (!pill) continue;

    if (info.online) {
      onlineCount++;
      pill.className = "status-pill status-online";
      statusText.textContent = info.ip.split(":")[0];
    } else {
      pill.className = "status-pill status-waiting";
      statusText.textContent = "OFFLINE";
    }
    ctrl.textContent = `${info.controller} · ${info.node_id}`;
    pin.textContent = info.pin_label;

    const sKeys = Object.keys(info.sensors || {});
    if (info.online && sKeys.length > 0) {
      const pairs = sKeys.map(k => {
        const v = info.sensors[k];
        return `${k}: ${Array.isArray(v) ? v.map(x => Number(x).toFixed(1)).join(", ") : v}`;
      });
      telem.style.display = "block";
      telem.textContent = pairs.join("  ·  ");
    } else {
      telem.style.display = "none";
    }
  }

  const badge = document.getElementById("nodes-summary-badge");
  if (badge) {
    badge.textContent = `${onlineCount}/${totalCount} Axes Online · UDP :4210`;
  }
}

// ============================================================================
// THREE.JS 3D REPLICA OF "SERVO MINI ARM BY LUCA DILO" (LIGHT STUDIO THEME)
// ============================================================================
const viewportEl = document.getElementById("viewport-root");
const container = document.getElementById("canvas-container");
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf4f5f7);
scene.fog = new THREE.FogExp2(0xf4f5f7, 0.012);

function getViewportSize() {
  return {
    w: viewportEl.clientWidth || (window.innerWidth - 372),
    h: viewportEl.clientHeight || (window.innerHeight - 52)
  };
}

const initSize = getViewportSize();
const camera = new THREE.PerspectiveCamera(40, initSize.w / initSize.h, 0.1, 200);
camera.position.set(13.5, 10.5, 15.5);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(initSize.w, initSize.h);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
container.appendChild(renderer.domElement);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.target.set(0, 4.6, 0);
controls.enableDamping = true;
controls.dampingFactor = 0.08;

function resetCameraView() {
  camera.position.set(13.5, 10.5, 15.5);
  controls.target.set(0, 4.6, 0);
  controls.update();
}

// Clean Daylight Studio Lighting
scene.add(new THREE.AmbientLight(0xffffff, 0.85));
const hemiLight = new THREE.HemisphereLight(0xffffff, 0xe4e4e7, 0.45);
hemiLight.position.set(0, 25, 0);
scene.add(hemiLight);

const dirLight = new THREE.DirectionalLight(0xffffff, 0.75);
dirLight.position.set(12, 24, 16);
dirLight.castShadow = true;
dirLight.shadow.mapSize.width = 2048;
dirLight.shadow.mapSize.height = 2048;
scene.add(dirLight);

// Light Architectural Workbench Surface & Precision CAD Grid
const tableGeo = new THREE.CylinderGeometry(16, 16, 0.25, 64);
const tableMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9, metalness: 0.02 });
const tableMesh = new THREE.Mesh(tableGeo, tableMat);
tableMesh.position.y = -0.125;
tableMesh.receiveShadow = true;
scene.add(tableMesh);

const grid = new THREE.GridHelper(28, 28, 0xd4d4d8, 0xe4e4e7);
grid.position.y = 0.01;
scene.add(grid);

// Target Calibration Cube on the Workbench
const cubeGeo = new THREE.BoxGeometry(1.5, 1.5, 1.5);
const cubeMat = new THREE.MeshStandardMaterial({ color: 0xdc2626, roughness: 0.35 });
const redCube = new THREE.Mesh(cubeGeo, cubeMat);
redCube.position.set(4.5, 0.75, 3.8);
redCube.castShadow = true;
scene.add(redCube);

// Materials matching the 3D-printed "Servo Mini Arm":
// 1. Industrial Cool Grey PLA (Spoked base & upper skeletal forearm)
const greyPlaMat = new THREE.MeshStandardMaterial({ color: 0x9ca3af, roughness: 0.45, metalness: 0.08 });
// 2. Matte Charcoal PLA (Turret pedestal, twin vertical shoulder links, geared gripper fingers)
const blackPlaMat = new THREE.MeshStandardMaterial({ color: 0x27272a, roughness: 0.5, metalness: 0.12 });
// 3. SG90 Servo Body
function makeServoMaterial() {
  return new THREE.MeshStandardMaterial({
    color: 0x2563eb,
    emissive: new THREE.Color(0x1d4ed8),
    emissiveIntensity: 0.08,
    roughness: 0.32,
    metalness: 0.15
  });
}
const hornMat = new THREE.MeshStandardMaterial({ color: 0xfafafa, roughness: 0.35 });

// Clickable Servo Meshes registry for Raycasting
const clickableServos = [];
const servoVisuals = {};

function createSG90ServoMesh(jointId) {
  const group = new THREE.Group();
  const mat = makeServoMaterial();

  const body = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.6, 2.3), mat);
  body.castShadow = true;
  body.userData.jointId = jointId;
  group.add(body);

  const ears = new THREE.Mesh(new THREE.BoxGeometry(1.25, 0.2, 3.1), mat);
  ears.position.y = 0.35;
  ears.userData.jointId = jointId;
  group.add(ears);

  const horn = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.35, 20), hornMat);
  horn.position.set(0, 0.92, 0.55);
  horn.userData.jointId = jointId;
  group.add(horn);

  const ringGeo = new THREE.RingGeometry(1.3, 1.46, 32);
  const ringMat = new THREE.MeshBasicMaterial({
    color: new THREE.Color(0x18181b),
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.15
  });
  const ring = new THREE.Mesh(ringGeo, ringMat);
  ring.rotation.x = Math.PI / 2;
  ring.position.y = 0.1;
  group.add(ring);

  clickableServos.push(body, ears, horn);
  servoVisuals[jointId] = { group, body, mat, ring, ringMat };
  return group;
}

// ============================================================================
// KINEMATIC CHAIN OF THE SERVO MINI ARM
// ============================================================================
const armRoot = new THREE.Group();
scene.add(armRoot);

const baseRingOuter = new THREE.Mesh(new THREE.CylinderGeometry(5.2, 5.2, 0.28, 48), greyPlaMat);
baseRingOuter.position.y = 0.14;
baseRingOuter.receiveShadow = true;
armRoot.add(baseRingOuter);

const baseInnerCut = new THREE.Mesh(new THREE.CylinderGeometry(4.2, 4.2, 0.30, 48), tableMat);
baseInnerCut.position.y = 0.14;
armRoot.add(baseInnerCut);

for (let i = 0; i < 4; i++) {
  const spoke = new THREE.Mesh(new THREE.BoxGeometry(10.2, 0.29, 0.95), greyPlaMat);
  spoke.position.y = 0.145;
  spoke.rotation.y = (i * Math.PI) / 4;
  armRoot.add(spoke);
}

const baseHub = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 1.8, 0.6, 32), greyPlaMat);
baseHub.position.y = 0.3;
armRoot.add(baseHub);

// --- JOINT 1: BASE YAW PIVOT (ESP32) ---
const baseYawPivot = new THREE.Group();
baseYawPivot.position.set(0, 0.6, 0);
armRoot.add(baseYawPivot);

const pedestal = new THREE.Mesh(new THREE.BoxGeometry(2.2, 2.0, 2.4), blackPlaMat);
pedestal.position.y = 1.0;
pedestal.castShadow = true;
baseYawPivot.add(pedestal);

const servo1 = createSG90ServoMesh("base");
servo1.position.set(0, 0.9, 0);
baseYawPivot.add(servo1);

const servo2 = createSG90ServoMesh("shoulder");
servo2.rotation.z = Math.PI / 2;
servo2.position.set(0.3, 2.1, 0);
baseYawPivot.add(servo2);

// --- JOINT 2: SHOULDER PITCH PIVOT (Raspberry Pi BCM 14) ---
const shoulderPivot = new THREE.Group();
shoulderPivot.position.set(0, 2.2, 0);
baseYawPivot.add(shoulderPivot);

const lowerArmLen = 5.4;
for (const side of [-1, 1]) {
  const lowerHalf = new THREE.Mesh(new THREE.BoxGeometry(0.28, lowerArmLen * 0.55, 0.62), blackPlaMat);
  lowerHalf.position.set(side * 1.15, lowerArmLen * 0.26, 0);
  lowerHalf.castShadow = true;
  shoulderPivot.add(lowerHalf);

  const upperHalf = new THREE.Mesh(new THREE.BoxGeometry(0.28, lowerArmLen * 0.55, 0.62), blackPlaMat);
  upperHalf.position.set(side * 0.95, lowerArmLen * 0.74, 0);
  upperHalf.castShadow = true;
  shoulderPivot.add(upperHalf);
}
const crossBrace = new THREE.Mesh(new THREE.BoxGeometry(2.3, 0.35, 0.55), blackPlaMat);
crossBrace.position.set(0, lowerArmLen * 0.48, 0);
shoulderPivot.add(crossBrace);

// --- JOINT 3: ELBOW PITCH PIVOT (RP2040 GP6) ---
const elbowPivot = new THREE.Group();
elbowPivot.position.set(0, lowerArmLen, 0);
shoulderPivot.add(elbowPivot);

const servo3 = createSG90ServoMesh("elbow");
servo3.position.set(0, 0.15, 0.9);
elbowPivot.add(servo3);

const forearmLen = 5.6;
for (const side of [-1, 1]) {
  const rail = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.95, forearmLen), greyPlaMat);
  rail.position.set(side * 0.82, 0.1, forearmLen / 2 - 0.3);
  rail.castShadow = true;
  elbowPivot.add(rail);
}
for (const zOff of [0.1, 2.2, 4.1, 5.1]) {
  const rib = new THREE.Mesh(new THREE.BoxGeometry(1.65, 0.85, 0.28), greyPlaMat);
  rib.position.set(0, 0.1, zOff);
  elbowPivot.add(rib);
}

// --- JOINT 4: GRIPPER CLAW PIVOT (Raspberry Pi BCM 18) ---
const gripperGroup = new THREE.Group();
gripperGroup.position.set(0, 0.1, forearmLen - 0.35);
elbowPivot.add(gripperGroup);

const servo4 = createSG90ServoMesh("gripper");
servo4.position.set(0, -0.75, -0.35);
gripperGroup.add(servo4);

const leftFingerPivot = new THREE.Group();
leftFingerPivot.position.set(-0.48, 0.15, 0.25);
gripperGroup.add(leftFingerPivot);

const rightFingerPivot = new THREE.Group();
rightFingerPivot.position.set(0.48, 0.15, 0.25);
gripperGroup.add(rightFingerPivot);

function buildClawFinger(isLeft) {
  const fg = new THREE.Group();
  const gear = new THREE.Mesh(new THREE.CylinderGeometry(0.48, 0.48, 0.28, 16), blackPlaMat);
  fg.add(gear);

  const armProx = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.28, 1.35), blackPlaMat);
  armProx.position.set(isLeft ? -0.18 : 0.18, 0, 0.68);
  fg.add(armProx);

  const jawTip = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.32, 1.15), blackPlaMat);
  jawTip.position.set(isLeft ? 0.05 : -0.05, 0, 1.55);
  jawTip.rotation.y = isLeft ? 0.32 : -0.32;
  fg.add(jawTip);
  return fg;
}
leftFingerPivot.add(buildClawFinger(true));
rightFingerPivot.add(buildClawFinger(false));

// ============================================================================
// 3D CALLOUT TAGS & FLOATING POPOVER POSITIONING
// ============================================================================
const tagsLayer = document.getElementById("tags-layer");
const tagElements = {};
for (const [jid, meta] of Object.entries(JOINTS_META)) {
  const el = document.createElement("div");
  el.className = "servo-tag";
  el.textContent = `${meta.code} · ${targetAngles[jid]}°`;
  el.onclick = () => selectServoJoint(jid);
  tagsLayer.appendChild(el);
  tagElements[jid] = el;
}

function selectServoJoint(jointId) {
  selectedJoint = jointId;
  const meta = JOINTS_META[jointId];
  const info = serverJointsData[jointId] || {};

  for (const k of Object.keys(JOINTS_META)) {
    const c = document.getElementById(`card-${k}`);
    if (c) c.classList.toggle("active", k === jointId);
    if (tagElements[k]) tagElements[k].classList.toggle("active", k === jointId);
  }

  const popup = document.getElementById("floating-popup");
  popup.style.display = "block";
  document.getElementById("popup-title").textContent = `${meta.code} · ${meta.name}`;
  document.getElementById("popup-sub").textContent =
    `${info.controller || meta.hw} (${info.node_id || ""}) · ${info.pin_label || ""}`;

  const pSlider = document.getElementById("popup-slider");
  pSlider.min = meta.min;
  pSlider.max = meta.max;
  pSlider.value = Math.round(targetAngles[jointId]);
  pSlider.oninput = (e) => sendJointAngle(jointId, parseInt(e.target.value, 10));

  const pAngle = document.getElementById("popup-angle");
  pAngle.textContent = Math.round(targetAngles[jointId]) + "°";

  document.getElementById("popup-btn-min").textContent = `${meta.min}°`;
  document.getElementById("popup-btn-min").onclick = () => sendJointAngle(jointId, meta.min);
  document.getElementById("popup-btn-m5").onclick = () => jogJoint(jointId, -5);
  document.getElementById("popup-btn-home").textContent = `Home (${meta.home}°)`;
  document.getElementById("popup-btn-home").onclick = () => sendJointAngle(jointId, meta.home);
  document.getElementById("popup-btn-p5").onclick = () => jogJoint(jointId, 5);
  document.getElementById("popup-btn-max").textContent = `${meta.max}°`;
  document.getElementById("popup-btn-max").onclick = () => sendJointAngle(jointId, meta.max);
}

function closePopup() {
  selectedJoint = null;
  document.getElementById("floating-popup").style.display = "none";
  for (const k of Object.keys(JOINTS_META)) {
    const c = document.getElementById(`card-${k}`);
    if (c) c.classList.remove("active");
    if (tagElements[k]) tagElements[k].classList.remove("active");
  }
}

const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();
let downPos = { x: 0, y: 0 };

renderer.domElement.addEventListener("pointerdown", (e) => {
  downPos = { x: e.clientX, y: e.clientY };
});
renderer.domElement.addEventListener("pointerup", (e) => {
  if (Math.hypot(e.clientX - downPos.x, e.clientY - downPos.y) > 6) return;
  const rect = renderer.domElement.getBoundingClientRect();
  mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(mouse, camera);
  const hits = raycaster.intersectObjects(clickableServos, false);
  if (hits.length > 0 && hits[0].object.userData.jointId) {
    selectServoJoint(hits[0].object.userData.jointId);
  }
});

function worldToViewport(worldVec) {
  const sz = getViewportSize();
  const v = worldVec.clone().project(camera);
  return {
    x: (v.x * 0.5 + 0.5) * sz.w,
    y: (-v.y * 0.5 + 0.5) * sz.h,
    visible: v.z < 1.0
  };
}

// ============================================================================
// 60 FPS KINEMATICS & RENDER LOOP
// ============================================================================
const tmpVec = new THREE.Vector3();

function animate() {
  requestAnimationFrame(animate);
  controls.update();

  for (const k of Object.keys(armState)) {
    armState[k] += (targetAngles[k] - armState[k]) * 0.18;
  }

  baseYawPivot.rotation.y = THREE.MathUtils.degToRad(armState.base - 90);

  const shoulderRad = THREE.MathUtils.degToRad(armState.shoulder - 90);
  shoulderPivot.rotation.x = shoulderRad;

  const elbowRad = THREE.MathUtils.degToRad(90 - armState.elbow);
  elbowPivot.rotation.x = elbowRad - shoulderRad * 0.45;

  const gripNorm = (armState.gripper - 10) / 85.0;
  const fingerAngle = (1.0 - gripNorm) * 0.55;
  leftFingerPivot.rotation.y = fingerAngle;
  rightFingerPivot.rotation.y = -fingerAngle;

  for (const [jid, vis] of Object.entries(servoVisuals)) {
    const isSel = selectedJoint === jid;
    vis.ringMat.opacity = isSel ? 0.75 : 0.14;
    vis.mat.emissiveIntensity = isSel ? 0.35 : 0.06;
  }

  const sz = getViewportSize();
  for (const [jid, vis] of Object.entries(servoVisuals)) {
    vis.group.getWorldPosition(tmpVec);
    tmpVec.y += 0.85;
    const sc = worldToViewport(tmpVec);
    const tag = tagElements[jid];
    if (sc.visible) {
      tag.style.display = "block";
      tag.style.left = `${sc.x + 42}px`;
      tag.style.top = `${sc.y}px`;
    } else {
      tag.style.display = "none";
    }

    if (selectedJoint === jid && sc.visible) {
      const popup = document.getElementById("floating-popup");
      const clampedX = Math.max(150, Math.min(sz.w - 150, sc.x));
      const clampedY = Math.max(155, Math.min(sz.h - 40, sc.y - 16));
      popup.style.left = `${clampedX}px`;
      popup.style.top = `${clampedY}px`;
    }
  }

  renderer.render(scene, camera);
}
animate();

window.addEventListener("resize", () => {
  const sz = getViewportSize();
  camera.aspect = sz.w / sz.h;
  camera.updateProjectionMatrix();
  renderer.setSize(sz.w, sz.h);
});
</script>
</body>
</html>
"""


class HydraArmStudioServer:
    def __init__(
        self,
        port: int = 8090,
        ip_overrides: Optional[Dict[str, str]] = None,
        step_delay_ms: int = 12,
    ):
        self.port = port
        self.step_delay_sec = max(0.004, step_delay_ms / 1000.0)
        addresses = controller_addresses(ip_overrides)
        self.master = SwarmMaster()
        self.joints: Dict[str, Dict[str, Any]] = {
            k: {**v, "target_angle": v["home_angle"], "pending": False} for k, v in JOINT_CONFIG.items()
        }
        self.websockets = set()

        # Episode Recording & Playback State
        self.recording: bool = False
        self.record_name: str = "episode_1"
        self.record_start_time: float = 0.0
        self.recorded_frames: List[Dict[str, Any]] = []
        self.last_saved_file: str = ""
        self.last_rec_message: str = "Ready • Saved episodes in projects/hydra_arm/episodes/"

        self.playing: bool = False
        self.playing_file: str = ""
        self.play_loop: bool = False
        self.play_progress: str = ""
        self._play_task: Optional[asyncio.Task] = None
        self._retired_playbacks = set()
        self._episodes_cache = []
        self._episodes_checked_at = 0.0

        # Pre-register any explicit IP overrides passed via CLI flags
        try:
            for node_id, ip_str in addresses.items():
                self.master.connect(node_id, ip=ip_str)
        except Exception:
            self.master.close()
            raise

        self.app = web.Application()
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/ws", self.handle_ws)
        self.app.cleanup_ctx.append(self._runtime)

    def _get_node(self, node_id: str):
        node = self.master.subscribe(node_id)
        if node is None and node_id == "arm_shoulder_gripper_rpi":
            node = self.master.subscribe("arm_gripper_rpi")
        return node

    def command_joint(self, joint_id: str, angle: int, from_playback: bool = False) -> bool:
        """Sets the target angle for smooth 1-degree-at-a-time trajectory interpolation."""
        if joint_id not in self.joints:
            return False
        cfg = self.joints[joint_id]
        clamped = max(cfg["min_angle"], min(cfg["max_angle"], int(angle)))
        cfg["target_angle"] = clamped
        cfg["pending"] = True

        if self.recording and not from_playback:
            t_rel = round(time.monotonic() - self.record_start_time, 3)
            pose = {jid: int(jcfg["target_angle"]) for jid, jcfg in self.joints.items()}
            # Avoid duplicate consecutive frames with identical pose
            if not self.recorded_frames or self.recorded_frames[-1]["joints"] != pose:
                self.recorded_frames.append({"t": t_rel, "joints": pose})

        return self._get_node(cfg["node_id"]) is not None

    def start_recording(self, name: str) -> None:
        self.stop_playback()
        clean_name = "".join(c if (c.isalnum() or c in ("_", "-")) else "_" for c in name.strip()) or "episode"
        self.record_name = clean_name
        self.recording = True
        self.record_start_time = time.monotonic()
        initial_pose = {jid: int(jcfg["target_angle"]) for jid, jcfg in self.joints.items()}
        self.recorded_frames = [{"t": 0.0, "joints": initial_pose}]
        self.last_rec_message = f"Recording '{clean_name}'..."
        print(f"[Episode Recorder] Started recording '{clean_name}' (initial pose: {initial_pose})")

    def stop_recording(self) -> Optional[str]:
        if not self.recording:
            return None
        self.recording = False
        duration = round(time.monotonic() - self.record_start_time, 3)
        # Ensure final pose at stop time is captured
        final_pose = {jid: int(jcfg["target_angle"]) for jid, jcfg in self.joints.items()}
        if not self.recorded_frames or self.recorded_frames[-1]["t"] < duration:
            self.recorded_frames.append({"t": duration, "joints": final_pose})

        fname = f"{self.record_name}.json"
        fpath = os.path.join(EPISODES_DIR, fname)
        payload = {
            "name": self.record_name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "duration_sec": duration,
            "steps": len(self.recorded_frames),
            "frames": self.recorded_frames,
        }
        os.makedirs(EPISODES_DIR, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=EPISODES_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(validate_episode(payload), f, indent=2, allow_nan=False)
            os.replace(temporary, fpath)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self._episodes_checked_at = 0.0

        self.last_saved_file = fname
        self.last_rec_message = f"Saved '{fname}' ({len(self.recorded_frames)} steps, {duration}s)"
        print(f"[Episode Recorder] Saved episode -> {fpath} ({len(self.recorded_frames)} steps, {duration}s)")
        return fname

    def list_episodes(self) -> List[Dict[str, Any]]:
        now = time.monotonic()
        if now - self._episodes_checked_at < 1.0:
            return list(self._episodes_cache)
        self._episodes_checked_at = now
        out: List[Dict[str, Any]] = []
        if not os.path.isdir(EPISODES_DIR):
            return out
        for fn in sorted(os.listdir(EPISODES_DIR)):
            if not fn.endswith(".json"):
                continue
            fpath = os.path.join(EPISODES_DIR, fn)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = validate_episode(json.load(f))
                out.append({
                    "filename": fn,
                    "name": data.get("name", fn[:-5]),
                    "steps": int(data.get("steps", len(data.get("frames", [])))),
                    "duration_sec": float(data.get("duration_sec", 0.0)),
                })
            except Exception:
                continue
        self._episodes_cache = out
        return list(out)

    def stop_playback(self) -> None:
        self.playing = False
        self.play_loop = False
        if self._play_task is not None and not self._play_task.done():
            self._play_task.cancel()
            self._retired_playbacks.add(self._play_task)
            self._play_task.add_done_callback(self._retired_playbacks.discard)
        self._play_task = None
        for cfg in self.joints.values():
            cfg["target_angle"] = cfg["angle"]
            cfg["pending"] = False
        self.last_rec_message = "Playback stopped"

    def start_playback(self, filename: str, loop_mode: bool = False) -> None:
        if self.recording:
            self.stop_recording()
        self.stop_playback()
        safe_fn = os.path.basename(filename)
        fpath = os.path.join(EPISODES_DIR, safe_fn)
        if not os.path.isfile(fpath):
            self.last_rec_message = f"Episode '{safe_fn}' not found"
            return
        self.playing = True
        self.playing_file = safe_fn
        self.play_loop = loop_mode
        self._play_task = asyncio.create_task(self._playback_runner(fpath, safe_fn, loop_mode))

    async def _playback_runner(self, fpath: str, safe_fn: str, loop_mode: bool) -> None:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = validate_episode(json.load(f))
            frames = data.get("frames", [])
            if not frames:
                self.last_rec_message = f"Episode '{safe_fn}' has 0 frames"
                self.playing = False
                return

            print(f"[Episode Player] Playing '{safe_fn}' ({len(frames)} frames, loop={loop_mode})")
            while self.playing:
                start_t = time.monotonic()
                for idx, frame in enumerate(frames):
                    if not self.playing:
                        break
                    target_t = float(frame.get("t", 0.0))
                    now_rel = time.monotonic() - start_t
                    wait_s = target_t - now_rel
                    if wait_s > 0:
                        await asyncio.sleep(wait_s)
                    if not self.playing:
                        break

                    joints_pose = frame.get("joints", {})
                    for jid, ang in joints_pose.items():
                        self.command_joint(jid, int(ang), from_playback=True)
                    self.play_progress = f"Step {idx + 1}/{len(frames)} ({target_t:.1f}s)"

                dwell = data["duration_sec"] - (time.monotonic() - start_t)
                if dwell > 0:
                    await asyncio.sleep(dwell)
                # Finish the final interpolation rather than assuming 500ms is enough.
                while any(cfg["pending"] for cfg in self.joints.values()):
                    await asyncio.sleep(self.step_delay_sec)
                if not loop_mode:
                    break

            self.last_rec_message = f"Finished playing '{safe_fn}'"
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.last_rec_message = f"Playback error: {exc}"
        finally:
            if asyncio.current_task() is self._play_task:
                self.playing = False
                self.play_progress = ""
                self._play_task = None

    def motion_tick(self) -> None:
        """Advance command estimates only when a live node can receive them."""
        for cfg in self.joints.values():
            if not cfg["pending"]:
                continue
            node = self._get_node(cfg["node_id"])
            if node is None or not node.is_online:
                continue
            angle = step_toward(int(cfg["angle"]), int(cfg["target_angle"]))
            node.servo(cfg["actuator_name"], angle)
            cfg["angle"] = angle
            cfg["pending"] = angle != cfg["target_angle"]

    async def smooth_motion_loop(self) -> None:
        """
        Smoothly steps each joint's current angle (`angle`) toward `target_angle`
        by up to 2 degrees per tick (~12 ms step delay) so sudden jumps (e.g. 90 -> 150)
        glide smoothly instead of snapping violently.
        """
        while True:
            self.motion_tick()
            await asyncio.sleep(self.step_delay_sec)

    def _build_status_payload(self) -> Dict[str, Any]:
        joints_out: Dict[str, Any] = {}
        for jid, cfg in self.joints.items():
            node = self._get_node(cfg["node_id"])
            online = bool(node is not None and node.is_online)
            joints_out[jid] = {
                **cfg,
                "online": online,
                "ip": f"{node.ip}:{node.port}" if node is not None else "--",
                "board": node.board if node is not None else "WAITING",
                "sensors": node.sensors if node is not None else {},
            }
        rec_out = {
            "recording": self.recording,
            "active_name": self.record_name,
            "frame_count": len(self.recorded_frames),
            "elapsed_sec": round(time.monotonic() - self.record_start_time, 1) if self.recording else 0.0,
            "playing": self.playing,
            "playing_file": self.playing_file,
            "loop": self.play_loop,
            "play_progress": self.play_progress,
            "last_saved": self.last_saved_file,
            "last_message": self.last_rec_message,
            "episodes": self.list_episodes(),
        }
        return {"joints": joints_out, "recorder": rec_out}

    async def handle_index(self, request: web.Request) -> web.Response:
        metadata = {k: {"id": k, "code": v["code"], "name": v["label"],
                        "hw": v["controller"] + " · " + v["pin_label"], "color": v["color"],
                        "min": v["min_angle"], "max": v["max_angle"], "home": v["home_angle"]}
                    for k, v in JOINT_CONFIG.items()}
        return web.Response(text=HTML_PAGE.replace("__JOINTS_META__", json.dumps(metadata)), content_type="text/html")

    async def handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.websockets.add(ws)
        await ws.send_str(json.dumps(self._build_status_payload()))

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(data, dict):
                        continue
                    op = data.get("op")
                    if op == "SET_JOINT":
                        joint_id = str(data.get("joint", ""))
                        angle = data.get("angle", 90)
                        if isinstance(angle, (int, float)) and not isinstance(angle, bool) and math.isfinite(angle):
                            self.command_joint(joint_id, int(angle))
                    elif op == "START_RECORD":
                        self.start_recording(str(data.get("name", "episode_1")))
                    elif op == "STOP_RECORD":
                        self.stop_recording()
                    elif op == "PLAY_EPISODE":
                        self.start_playback(
                            str(data.get("filename", "")),
                            loop_mode=bool(data.get("loop", False)),
                        )
                    elif op == "STOP_PLAYBACK":
                        self.stop_playback()
        finally:
            self.websockets.discard(ws)
        return ws

    async def telemetry_broadcast_loop(self) -> None:
        while True:
            if self.websockets:
                payload = json.dumps(self._build_status_payload())
                for ws in list(self.websockets):
                    try:
                        await ws.send_str(payload)
                    except Exception:
                        self.websockets.discard(ws)
            await asyncio.sleep(0.1)

    async def _cleanup(self, app: web.Application) -> None:
        self.master.close()

    async def _runtime(self, app):
        tasks = [asyncio.create_task(self.smooth_motion_loop()),
                 asyncio.create_task(self.telemetry_broadcast_loop())]
        try:
            yield
        finally:
            self.stop_playback()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, *self._retired_playbacks, return_exceptions=True)
            for ws in list(self.websockets):
                await ws.close()
            self.master.close()

    def run(self) -> None:
        print("=" * 74)
        print("  OpenSwarm HydraArm Studio — 4-Joint / 3-Controller Distributed Robotic Arm")
        print("=" * 74)
        print(f"  3D Interactive Studio URL : http://localhost:{self.port}")
        print("  Expected Slave Nodes on Wi-Fi (UDP 4210 / 4211):")
        for jid, cfg in self.joints.items():
            print(f"    - {cfg['label']:24s} -> {cfg['node_id']:20s} ({cfg['controller']}, {cfg['pin_label']})")
        print("=" * 74)
        web.run_app(self.app, host="127.0.0.1", port=self.port)


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenSwarm HydraArm 3D Interactive Studio")
    parser.add_argument("--port", type=int, default=8090, help="Local web server port (default: 8090)")
    parser.add_argument("--base-ip", type=str, default=None, help="Optional direct IP for arm_base_esp32")
    parser.add_argument("--shoulder-ip", type=str, default=None, help="Optional direct IP for arm_shoulder_gripper_rpi")
    parser.add_argument("--elbow-ip", type=str, default=None, help="Optional direct IP for arm_elbow_rp2040")
    parser.add_argument("--gripper-ip", type=str, default=None, help="Optional direct IP for arm_shoulder_gripper_rpi")
    args = parser.parse_args()

    overrides = {
        "base": args.base_ip,
        "shoulder": args.shoulder_ip,
        "elbow": args.elbow_ip,
        "gripper": args.gripper_ip,
    }
    studio = HydraArmStudioServer(port=args.port, ip_overrides=overrides)
    studio.run()


if __name__ == "__main__":
    main()
