#!/usr/bin/env python3
"""
===============================================================================
OpenSwarm HydraArm Studio — 3D Interactive Digital Twin & Multi-Controller Master
===============================================================================
Controls the 4-DOF "Servo Mini Arm" where each servo is wired to a different
heterogeneous Slave controller over Wi-Fi UDP:
  - Joint 1 (Base Yaw)       -> ESP32             (node_id: "arm_base_esp32")
  - Joint 2 (Shoulder Pitch) -> Arduino UNO Q     (node_id: "arm_shoulder_unoq")
  - Joint 3 (Elbow Pitch)    -> RP2040            (node_id: "arm_elbow_rp2040")
  - Joint 4 (Gripper Claw)   -> Raspberry Pi      (node_id: "arm_gripper_rpi")

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
import os
import sys
import time
from typing import Dict, Any, Optional

from aiohttp import web

# Ensure local `master/` package is importable even if not pip-installed yet
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MASTER_PKG_DIR = os.path.join(REPO_ROOT, "master")
if MASTER_PKG_DIR not in sys.path:
    sys.path.insert(0, MASTER_PKG_DIR)

from openswarm.master import SwarmMaster

logger = logging.getLogger("hydra_arm_studio")


JOINT_CONFIG: Dict[str, Dict[str, Any]] = {
    "base": {
        "joint_id": "base",
        "label": "Joint 1: Base Yaw",
        "node_id": "arm_base_esp32",
        "controller": "ESP32",
        "pin_label": "GPIO 13",
        "color": "#38bdf8",
        "min_angle": 0,
        "max_angle": 180,
        "home_angle": 90,
        "angle": 90,
        "description": "Rotates the entire upper arm assembly left/right on the circular base.",
    },
    "shoulder": {
        "joint_id": "shoulder",
        "label": "Joint 2: Shoulder Pitch",
        "node_id": "arm_shoulder_unoq",
        "controller": "Arduino UNO Q",
        "pin_label": "Pin D9 (MCU Bridge)",
        "color": "#a855f7",
        "min_angle": 20,
        "max_angle": 160,
        "home_angle": 90,
        "angle": 90,
        "description": "Drives the twin black vertical linkage bars forward and backward.",
    },
    "elbow": {
        "joint_id": "elbow",
        "label": "Joint 3: Elbow Pitch",
        "node_id": "arm_elbow_rp2040",
        "controller": "RP2040 (Nano / Pico W)",
        "pin_label": "Pin D6 / GP6",
        "color": "#f97316",
        "min_angle": 20,
        "max_angle": 160,
        "home_angle": 90,
        "angle": 90,
        "description": "Raises and lowers the grey skeletal forearm link.",
    },
    "gripper": {
        "joint_id": "gripper",
        "label": "Joint 4: Gripper Claw",
        "node_id": "arm_gripper_rpi",
        "controller": "Raspberry Pi (Ubuntu 24.04)",
        "pin_label": "BCM GPIO 18 (Pin 12)",
        "color": "#22c55e",
        "min_angle": 10,
        "max_angle": 95,
        "home_angle": 45,
        "angle": 45,
        "description": "Opens (10°) and closes (95°) the geared parallel gripper fingers.",
    },
}


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>OpenSwarm HydraArm Studio — 4-Controller Distributed Robotic Arm</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<style>
  :root {
    --bg: #0b0f19;
    --panel: rgba(15, 23, 42, 0.88);
    --border: rgba(148, 163, 184, 0.18);
    --text: #f8fafc;
    --muted: #94a3b8;
    --accent: #38bdf8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    overflow: hidden;
    height: 100vh;
    width: 100vw;
  }
  #canvas-container {
    position: absolute;
    inset: 0;
  }

  /* Top Header Bar */
  .topbar {
    position: absolute;
    top: 16px;
    left: 16px;
    right: 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    background: var(--panel);
    backdrop-filter: blur(14px);
    border: 1px solid var(--border);
    border-radius: 14px;
    z-index: 10;
    pointer-events: auto;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .brand-badge {
    background: linear-gradient(135deg, #0ea5e9, #6366f1);
    color: white;
    font-weight: 800;
    font-size: 13px;
    padding: 6px 11px;
    border-radius: 8px;
    letter-spacing: 0.6px;
  }
  .brand-title {
    font-size: 17px;
    font-weight: 700;
  }
  .brand-sub {
    font-size: 12px;
    color: var(--muted);
  }
  .top-actions {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .btn {
    background: rgba(30, 41, 59, 0.9);
    color: var(--text);
    border: 1px solid var(--border);
    padding: 8px 14px;
    border-radius: 9px;
    font-size: 12.5px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .btn:hover {
    background: rgba(51, 65, 85, 0.95);
    border-color: var(--accent);
  }
  .btn-primary {
    background: linear-gradient(135deg, #0284c7, #2563eb);
    border-color: rgba(56, 189, 248, 0.4);
  }
  .btn-danger {
    background: rgba(185, 28, 28, 0.85);
    border-color: rgba(248, 113, 113, 0.4);
  }

  /* Left Sidebar: 4 Distributed Controllers Status & Joint Rack */
  .sidebar {
    position: absolute;
    top: 84px;
    left: 16px;
    bottom: 16px;
    width: 350px;
    background: var(--panel);
    backdrop-filter: blur(14px);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    overflow-y: auto;
    z-index: 10;
  }
  .section-title {
    font-size: 11.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.9px;
    color: var(--muted);
  }
  .hint-banner {
    background: rgba(56, 189, 248, 0.1);
    border: 1px solid rgba(56, 189, 248, 0.3);
    border-radius: 10px;
    padding: 10px 12px;
    font-size: 12px;
    line-height: 1.45;
    color: #e0f2fe;
  }

  .joint-card {
    background: rgba(30, 41, 59, 0.65);
    border: 1.5px solid rgba(148, 163, 184, 0.16);
    border-radius: 12px;
    padding: 12px;
    cursor: pointer;
    transition: all 0.16s ease;
  }
  .joint-card:hover {
    border-color: rgba(148, 163, 184, 0.45);
  }
  .joint-card.active {
    background: rgba(30, 41, 59, 0.95);
    box-shadow: 0 0 0 1px currentColor, 0 8px 24px -6px rgba(0, 0, 0, 0.6);
  }
  .joint-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .joint-name {
    font-size: 13.5px;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .color-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    display: inline-block;
  }
  .status-pill {
    font-size: 10.5px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 999px;
    letter-spacing: 0.4px;
  }
  .status-online {
    background: rgba(34, 197, 94, 0.18);
    color: #4ade80;
    border: 1px solid rgba(34, 197, 94, 0.4);
  }
  .status-waiting {
    background: rgba(245, 158, 11, 0.16);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.35);
  }
  .joint-meta {
    font-size: 11.5px;
    color: var(--muted);
    display: flex;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  .slider-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .slider-row input[type="range"] {
    flex: 1;
    accent-color: var(--accent);
    cursor: pointer;
    height: 6px;
  }
  .angle-readout {
    font-family: 'JetBrains Mono', Consolas, monospace;
    font-size: 13px;
    font-weight: 700;
    min-width: 44px;
    text-align: right;
  }
  .telemetry-line {
    margin-top: 6px;
    font-size: 11px;
    font-family: 'JetBrains Mono', Consolas, monospace;
    color: #cbd5e1;
    background: rgba(15, 23, 42, 0.55);
    padding: 4px 8px;
    border-radius: 6px;
  }

  /* Floating 3D Click Popup Slider (Appears right over the clicked Servo Motor!) */
  #floating-popup {
    position: absolute;
    width: 280px;
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(16px);
    border: 2px solid var(--accent);
    border-radius: 14px;
    padding: 14px 16px;
    box-shadow: 0 18px 40px rgba(0, 0, 0, 0.65);
    z-index: 25;
    display: none;
    pointer-events: auto;
    transform: translate(-50%, -115%);
  }
  #floating-popup::after {
    content: "";
    position: absolute;
    bottom: -9px;
    left: 50%;
    transform: translateX(-50%);
    border-width: 9px 9px 0;
    border-style: solid;
    border-color: var(--accent) transparent;
  }
  .popup-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }
  .popup-title {
    font-size: 14px;
    font-weight: 800;
  }
  .popup-close {
    background: none;
    border: none;
    color: var(--muted);
    font-size: 16px;
    cursor: pointer;
    padding: 0 4px;
  }
  .popup-sub {
    font-size: 11.5px;
    color: var(--muted);
    margin-bottom: 10px;
  }
  .popup-slider-wrap {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
  }
  .popup-slider-wrap input[type="range"] {
    flex: 1;
    cursor: pointer;
  }
  .popup-angle-badge {
    font-family: 'JetBrains Mono', Consolas, monospace;
    font-size: 16px;
    font-weight: 800;
    color: #38bdf8;
    min-width: 50px;
    text-align: right;
  }
  .popup-quick-btns {
    display: flex;
    justify-content: space-between;
    gap: 6px;
  }
  .popup-quick-btns button {
    flex: 1;
    background: rgba(30, 41, 59, 0.9);
    border: 1px solid var(--border);
    color: var(--text);
    font-size: 11px;
    font-weight: 600;
    padding: 5px 0;
    border-radius: 6px;
    cursor: pointer;
  }
  .popup-quick-btns button:hover {
    border-color: var(--accent);
  }

  /* 3D Servo Labels in Viewport */
  .servo-tag {
    position: absolute;
    padding: 4px 9px;
    background: rgba(15, 23, 42, 0.86);
    border: 1.5px solid #38bdf8;
    border-radius: 999px;
    color: #f8fafc;
    font-size: 11px;
    font-weight: 700;
    pointer-events: auto;
    cursor: pointer;
    transform: translate(-50%, -50%);
    white-space: nowrap;
    transition: transform 0.12s ease, box-shadow 0.12s ease;
    z-index: 15;
  }
  .servo-tag:hover {
    transform: translate(-50%, -50%) scale(1.08);
    box-shadow: 0 0 14px rgba(56, 189, 248, 0.55);
  }
</style>
</head>
<body>

<div id="canvas-container"></div>

<!-- Top Navigation & Preset Bar -->
<div class="topbar">
  <div class="brand">
    <span class="brand-badge">OPENSWARM HYDRA-ARM</span>
    <div>
      <div class="brand-title">4-Controller Distributed Servo Mini Arm Studio</div>
      <div class="brand-sub">ESP32 (Base) + Arduino UNO Q (Shoulder) + RP2040 (Elbow) + Raspberry Pi Ubuntu 24 (Gripper)</div>
    </div>
  </div>
  <div class="top-actions">
    <button class="btn btn-primary" onclick="sendPreset(90, 90, 90, 45)">Home Pose</button>
    <button class="btn" onclick="sendPreset(90, 125, 65, 20)">Reach Cube</button>
    <button class="btn" onclick="sendPreset(90, 125, 65, 85)">Grab Cube</button>
    <button class="btn" onclick="sendPreset(135, 75, 115, 85)">Lift &amp; Swing Left</button>
    <button class="btn" onclick="sendPreset(45, 115, 75, 20)">Drop Right</button>
  </div>
</div>

<!-- Left Sidebar: All 4 Controllers + Direct Sliders -->
<div class="sidebar">
  <div class="section-title">Interactive 3D Servo Control</div>
  <div class="hint-banner">
    <strong>Click any blue SG90 servo motor</strong> directly on the 3D arm (or its floating badge) to pop up its joint slider and move the real robot!
  </div>
  <div id="joint-cards-container" style="display:flex; flex-direction:column; gap:10px;"></div>
</div>

<!-- Floating Slider Popup over Clicked 3D Servo -->
<div id="floating-popup">
  <div class="popup-header">
    <div class="popup-title" id="popup-title">Joint 1: Base Yaw</div>
    <button class="popup-close" onclick="closePopup()">✕</button>
  </div>
  <div class="popup-sub" id="popup-sub">ESP32 #1 (arm_base_esp32) • GPIO 13</div>
  <div class="popup-slider-wrap">
    <input type="range" id="popup-slider" min="0" max="180" value="90" />
    <div class="popup-angle-badge" id="popup-angle">90°</div>
  </div>
  <div class="popup-quick-btns">
    <button id="popup-btn-min">Min</button>
    <button id="popup-btn-home">Home (90°)</button>
    <button id="popup-btn-max">Max</button>
  </div>
</div>

<!-- 3D Clickable Pill Tags Anchored to Each Servo -->
<div id="tags-layer"></div>

<script>
const JOINTS_META = {
  base:     { id: "base",     short: "J1 Base (ESP32)",        color: "#38bdf8", min: 0,  max: 180, home: 90 },
  shoulder: { id: "shoulder", short: "J2 Shoulder (UNO Q)",    color: "#a855f7", min: 20, max: 160, home: 90 },
  elbow:    { id: "elbow",    short: "J3 Elbow (RP2040)",      color: "#f97316", min: 20, max: 160, home: 90 },
  gripper:  { id: "gripper",  short: "J4 Gripper (RPi)",       color: "#22c55e", min: 10, max: 95,  home: 45 }
};

let armState = {
  base: 90,
  shoulder: 90,
  elbow: 90,
  gripper: 45
};
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
        if (selectedJoint !== jid) {
          targetAngles[jid] = jinfo.angle;
        }
      }
      renderSidebarCards();
    }
  };
  ws.onclose = () => setTimeout(connectWS, 1000);
}
connectWS();

function sendJointAngle(jointId, angle) {
  const meta = JOINTS_META[jointId];
  const clamped = Math.max(meta.min, Math.min(meta.max, Math.round(angle)));
  targetAngles[jointId] = clamped;

  if (selectedJoint === jointId) {
    document.getElementById("popup-slider").value = clamped;
    document.getElementById("popup-angle").textContent = clamped + "°";
  }
  const sSlider = document.getElementById(`slider-${jointId}`);
  const sReadout = document.getElementById(`readout-${jointId}`);
  if (sSlider) sSlider.value = clamped;
  if (sReadout) sReadout.textContent = clamped + "°";

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ op: "SET_JOINT", joint: jointId, angle: clamped }));
  }
}

function sendPreset(b, s, e, g) {
  sendJointAngle("base", b);
  sendJointAngle("shoulder", s);
  sendJointAngle("elbow", e);
  sendJointAngle("gripper", g);
}

// ============================================================================
// SIDEBAR CARDS RENDERER
// ============================================================================
function buildSidebarCards() {
  const container = document.getElementById("joint-cards-container");
  container.innerHTML = "";
  for (const [jid, meta] of Object.entries(JOINTS_META)) {
    const card = document.createElement("div");
    card.className = "joint-card";
    card.id = `card-${jid}`;
    card.style.color = meta.color;
    card.onclick = (ev) => {
      if (ev.target.tagName.toLowerCase() !== "input") {
        selectServoJoint(jid);
      }
    };
    card.innerHTML = `
      <div class="joint-header">
        <div class="joint-name" style="color:#f8fafc;">
          <span class="color-dot" style="background:${meta.color};"></span>
          <span id="title-${jid}">${meta.short}</span>
        </div>
        <span class="status-pill status-waiting" id="status-${jid}">WAITING</span>
      </div>
      <div class="joint-meta">
        <span id="ctrl-${jid}">Node: arm_${jid}</span>
        <span id="pin-${jid}">Pin: --</span>
      </div>
      <div class="slider-row">
        <input type="range" id="slider-${jid}" min="${meta.min}" max="${meta.max}" value="${targetAngles[jid]}"
               style="accent-color:${meta.color}"
               oninput="onSidebarSlider('${jid}', this.value)" />
        <span class="angle-readout" id="readout-${jid}" style="color:${meta.color}">${targetAngles[jid]}°</span>
      </div>
      <div class="telemetry-line" id="telem-${jid}">Waiting for UDP broadcast on port 4211...</div>
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
  for (const [jid, info] of Object.entries(serverJointsData)) {
    const pill = document.getElementById(`status-${jid}`);
    const ctrl = document.getElementById(`ctrl-${jid}`);
    const pin = document.getElementById(`pin-${jid}`);
    const telem = document.getElementById(`telem-${jid}`);
    if (!pill) continue;

    if (info.online) {
      pill.className = "status-pill status-online";
      pill.textContent = `ONLINE • ${info.ip}`;
    } else {
      pill.className = "status-pill status-waiting";
      pill.textContent = "OFFLINE / SIM";
    }
    ctrl.textContent = `${info.controller} (${info.node_id})`;
    pin.textContent = info.pin_label;

    const sKeys = Object.keys(info.sensors || {});
    if (info.online && sKeys.length > 0) {
      const pairs = sKeys.map(k => {
        const v = info.sensors[k];
        return `${k}: ${Array.isArray(v) ? v.map(x => Number(x).toFixed(1)).join(",") : v}`;
      });
      telem.textContent = pairs.join(" | ");
    } else {
      telem.textContent = `3D Twin Active • Ready for '${info.node_id}' on UDP 4210`;
    }
  }
}

// ============================================================================
// THREE.JS 3D REPLICA OF "SERVO MINI ARM BY LUCA DILO"
// ============================================================================
const container = document.getElementById("canvas-container");
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0f19);
scene.fog = new THREE.FogExp2(0x0b0f19, 0.018);

const camera = new THREE.PerspectiveCamera(42, window.innerWidth / window.innerHeight, 0.1, 200);
camera.position.set(14.5, 11.5, 16.5);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
container.appendChild(renderer.domElement);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.target.set(0, 4.8, 0);
controls.enableDamping = true;
controls.dampingFactor = 0.07;

// Lights
scene.add(new THREE.AmbientLight(0xffffff, 0.65));
const dirLight = new THREE.DirectionalLight(0xffffff, 0.95);
dirLight.position.set(12, 22, 16);
dirLight.castShadow = true;
scene.add(dirLight);

const rimLight = new THREE.DirectionalLight(0x38bdf8, 0.4);
rimLight.position.set(-14, 10, -10);
scene.add(rimLight);

// Workbench Surface & Subtle Grid
const tableGeo = new THREE.CylinderGeometry(18, 18, 0.3, 64);
const tableMat = new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 0.85, metalness: 0.1 });
const tableMesh = new THREE.Mesh(tableGeo, tableMat);
tableMesh.position.y = -0.15;
tableMesh.receiveShadow = true;
scene.add(tableMesh);

const grid = new THREE.GridHelper(30, 30, 0x1e293b, 0x1e293b);
grid.position.y = 0.01;
scene.add(grid);

// Red Target Cube on the Table (Matches the red cube in the MakerWorld photo!)
const cubeGeo = new THREE.BoxGeometry(1.6, 1.6, 1.6);
const cubeMat = new THREE.MeshStandardMaterial({ color: 0xdc2626, roughness: 0.4 });
const redCube = new THREE.Mesh(cubeGeo, cubeMat);
redCube.position.set(4.5, 0.8, 3.8);
redCube.castShadow = true;
scene.add(redCube);

// Materials matching the 3D-printed "Servo Mini Arm" photo:
// 1. Grey PLA (Round spoked base & upper skeletal forearm)
const greyPlaMat = new THREE.MeshStandardMaterial({ color: 0x7c8594, roughness: 0.45, metalness: 0.1 });
// 2. Matte Black PLA (Turret pedestal, twin vertical shoulder links, geared gripper fingers)
const blackPlaMat = new THREE.MeshStandardMaterial({ color: 0x18181b, roughness: 0.55, metalness: 0.15 });
// 3. Translucent Blue SG90 Servo Body
function makeServoMaterial(hexColor) {
  return new THREE.MeshStandardMaterial({
    color: 0x1d4ed8,
    emissive: new THREE.Color(hexColor),
    emissiveIntensity: 0.22,
    roughness: 0.3,
    metalness: 0.2
  });
}
const hornMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.4 });

// Clickable Servo Meshes registry for Raycasting
const clickableServos = [];
const servoVisuals = {};

function createSG90ServoMesh(jointId, hexColor) {
  const group = new THREE.Group();
  const mat = makeServoMaterial(hexColor);

  // Main blue SG90 body
  const body = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.6, 2.3), mat);
  body.castShadow = true;
  body.userData.jointId = jointId;
  group.add(body);

  // Mounting ears
  const ears = new THREE.Mesh(new THREE.BoxGeometry(1.25, 0.2, 3.1), mat);
  ears.position.y = 0.35;
  ears.userData.jointId = jointId;
  group.add(ears);

  // White output horn boss
  const horn = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.35, 20), hornMat);
  horn.position.set(0, 0.92, 0.55);
  horn.userData.jointId = jointId;
  group.add(horn);

  // Glowing selection ring around the servo
  const ringGeo = new THREE.RingGeometry(1.35, 1.55, 32);
  const ringMat = new THREE.MeshBasicMaterial({
    color: new THREE.Color(hexColor),
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.35
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

// 1. Spoked Circular Grey Base Plate (matches photo!)
const baseRingOuter = new THREE.Mesh(new THREE.CylinderGeometry(5.2, 5.2, 0.28, 48), greyPlaMat);
baseRingOuter.position.y = 0.14;
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

// Center Base Hub
const baseHub = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 1.8, 0.6, 32), greyPlaMat);
baseHub.position.y = 0.3;
armRoot.add(baseHub);

// --- JOINT 1: BASE YAW PIVOT (ESP32 #1) ---
const baseYawPivot = new THREE.Group();
baseYawPivot.position.set(0, 0.6, 0);
armRoot.add(baseYawPivot);

// Black Turret Pedestal
const pedestal = new THREE.Mesh(new THREE.BoxGeometry(2.2, 2.0, 2.4), blackPlaMat);
pedestal.position.y = 1.0;
pedestal.castShadow = true;
baseYawPivot.add(pedestal);

// Servo #1 (Base Yaw — ESP32 #1) inside bottom of pedestal
const servo1 = createSG90ServoMesh("base", JOINTS_META.base.color);
servo1.position.set(0, 0.9, 0);
baseYawPivot.add(servo1);

// Servo #2 (Shoulder Pitch — ESP32 #2) mounted horizontally in upper pedestal
const servo2 = createSG90ServoMesh("shoulder", JOINTS_META.shoulder.color);
servo2.rotation.z = Math.PI / 2;
servo2.position.set(0.3, 2.1, 0);
baseYawPivot.add(servo2);

// --- JOINT 2: SHOULDER PITCH PIVOT (ESP32 #2) ---
const shoulderPivot = new THREE.Group();
shoulderPivot.position.set(0, 2.2, 0);
baseYawPivot.add(shoulderPivot);

// Twin Black A-Frame Vertical Linkage Struts (Characteristic look of Luca Dilo's Servo Mini Arm!)
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
// Crossbrace on the black vertical link
const crossBrace = new THREE.Mesh(new THREE.BoxGeometry(2.3, 0.35, 0.55), blackPlaMat);
crossBrace.position.set(0, lowerArmLen * 0.48, 0);
shoulderPivot.add(crossBrace);

// --- JOINT 3: ELBOW PITCH PIVOT (RP2040) ---
const elbowPivot = new THREE.Group();
elbowPivot.position.set(0, lowerArmLen, 0);
shoulderPivot.add(elbowPivot);

// Servo #3 (Elbow Pitch — RP2040) nestled in the rear of the grey forearm
const servo3 = createSG90ServoMesh("elbow", JOINTS_META.elbow.color);
servo3.position.set(0, 0.15, 0.9);
elbowPivot.add(servo3);

// Grey Skeletal Forearm Rails (extends forward along +Z)
const forearmLen = 5.6;
for (const side of [-1, 1]) {
  const rail = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.95, forearmLen), greyPlaMat);
  rail.position.set(side * 0.82, 0.1, forearmLen / 2 - 0.3);
  rail.castShadow = true;
  elbowPivot.add(rail);
}
// Forearm cross-ribs
for (const zOff of [0.1, 2.2, 4.1, 5.1]) {
  const rib = new THREE.Mesh(new THREE.BoxGeometry(1.65, 0.85, 0.28), greyPlaMat);
  rib.position.set(0, 0.1, zOff);
  elbowPivot.add(rib);
}

// --- JOINT 4: GRIPPER CLAW PIVOT (Raspberry Pi Ubuntu 24.04) ---
const gripperGroup = new THREE.Group();
gripperGroup.position.set(0, 0.1, forearmLen - 0.35);
elbowPivot.add(gripperGroup);

// Servo #4 (Gripper — Raspberry Pi) mounted underneath the front tip of the forearm
const servo4 = createSG90ServoMesh("gripper", JOINTS_META.gripper.color);
servo4.position.set(0, -0.75, -0.35);
gripperGroup.add(servo4);

// Twin Meshed Black Gears + Parallel Gripper Fingers
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
// 3D PILL TAGS & FLOATING SLIDER POPUP POSITIONING
// ============================================================================
const tagsLayer = document.getElementById("tags-layer");
const tagElements = {};
for (const [jid, meta] of Object.entries(JOINTS_META)) {
  const el = document.createElement("div");
  el.className = "servo-tag";
  el.style.borderColor = meta.color;
  el.innerHTML = `<span style="color:${meta.color}">●</span> ${meta.short}`;
  el.onclick = () => selectServoJoint(jid);
  tagsLayer.appendChild(el);
  tagElements[jid] = el;
}

function selectServoJoint(jointId) {
  selectedJoint = jointId;
  const meta = JOINTS_META[jointId];
  const info = serverJointsData[jointId] || {};

  // Highlight active sidebar card
  for (const k of Object.keys(JOINTS_META)) {
    const c = document.getElementById(`card-${k}`);
    if (c) c.classList.toggle("active", k === jointId);
  }

  // Configure floating popup
  const popup = document.getElementById("floating-popup");
  popup.style.display = "block";
  popup.style.borderColor = meta.color;
  document.getElementById("popup-title").textContent = info.label || meta.short;
  document.getElementById("popup-title").style.color = meta.color;
  document.getElementById("popup-sub").textContent =
    `${info.controller || ""} (${info.node_id || ""}) • ${info.pin_label || ""}`;

  const pSlider = document.getElementById("popup-slider");
  pSlider.min = meta.min;
  pSlider.max = meta.max;
  pSlider.value = Math.round(targetAngles[jointId]);
  pSlider.style.accentColor = meta.color;
  pSlider.oninput = (e) => sendJointAngle(jointId, parseInt(e.target.value, 10));

  const pAngle = document.getElementById("popup-angle");
  pAngle.textContent = Math.round(targetAngles[jointId]) + "°";
  pAngle.style.color = meta.color;

  document.getElementById("popup-btn-min").textContent = `Min (${meta.min}°)`;
  document.getElementById("popup-btn-min").onclick = () => sendJointAngle(jointId, meta.min);
  document.getElementById("popup-btn-home").textContent = `Home (${meta.home}°)`;
  document.getElementById("popup-btn-home").onclick = () => sendJointAngle(jointId, meta.home);
  document.getElementById("popup-btn-max").textContent = `Max (${meta.max}°)`;
  document.getElementById("popup-btn-max").onclick = () => sendJointAngle(jointId, meta.max);
}

function closePopup() {
  selectedJoint = null;
  document.getElementById("floating-popup").style.display = "none";
  for (const k of Object.keys(JOINTS_META)) {
    const c = document.getElementById(`card-${k}`);
    if (c) c.classList.remove("active");
  }
}

// Raycaster so clicking directly on any 3D blue servo motor opens its slider
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();
let downPos = { x: 0, y: 0 };

renderer.domElement.addEventListener("pointerdown", (e) => {
  downPos = { x: e.clientX, y: e.clientY };
});
renderer.domElement.addEventListener("pointerup", (e) => {
  if (Math.hypot(e.clientX - downPos.x, e.clientY - downPos.y) > 6) return;
  mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
  mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
  raycaster.setFromCamera(mouse, camera);
  const hits = raycaster.intersectObjects(clickableServos, false);
  if (hits.length > 0 && hits[0].object.userData.jointId) {
    selectServoJoint(hits[0].object.userData.jointId);
  }
});

function worldToScreen(worldVec) {
  const v = worldVec.clone().project(camera);
  return {
    x: (v.x * 0.5 + 0.5) * window.innerWidth,
    y: (-v.y * 0.5 + 0.5) * window.innerHeight,
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

  // Smoothly interpolate visual joint angles toward targetAngles
  for (const k of Object.keys(armState)) {
    armState[k] += (targetAngles[k] - armState[k]) * 0.18;
  }

  // 1. Base Yaw (90 deg = facing forward +Z)
  baseYawPivot.rotation.y = THREE.MathUtils.degToRad(armState.base - 90);

  // 2. Shoulder Pitch (90 deg = upright, >90 tilts forward)
  const shoulderRad = THREE.MathUtils.degToRad(armState.shoulder - 90);
  shoulderPivot.rotation.x = shoulderRad;

  // 3. Elbow Pitch (90 deg = horizontal forearm, <90 tilts down toward table)
  const elbowRad = THREE.MathUtils.degToRad(90 - armState.elbow);
  elbowPivot.rotation.x = elbowRad - shoulderRad * 0.45;

  // 4. Gripper Claw (10 deg = open wide, 95 deg = closed)
  const gripNorm = (armState.gripper - 10) / 85.0; // 0 = open, 1 = closed
  const fingerAngle = (1.0 - gripNorm) * 0.55;
  leftFingerPivot.rotation.y = fingerAngle;
  rightFingerPivot.rotation.y = -fingerAngle;

  // Pulse selected servo ring
  const pulse = 0.55 + 0.35 * Math.sin(performance.now() * 0.006);
  for (const [jid, vis] of Object.entries(servoVisuals)) {
    const isSel = selectedJoint === jid;
    vis.ringMat.opacity = isSel ? 0.95 : 0.3;
    vis.ring.scale.setScalar(isSel ? 1.0 + 0.12 * pulse : 1.0);
    vis.mat.emissiveIntensity = isSel ? 0.55 : 0.2;
  }

  // Update 2D screen positions of servo pill tags & floating popup
  for (const [jid, vis] of Object.entries(servoVisuals)) {
    vis.group.getWorldPosition(tmpVec);
    tmpVec.y += 0.85;
    const sc = worldToScreen(tmpVec);
    const tag = tagElements[jid];
    if (sc.visible) {
      tag.style.display = "block";
      tag.style.left = `${sc.x + 48}px`;
      tag.style.top = `${sc.y}px`;
    } else {
      tag.style.display = "none";
    }

    if (selectedJoint === jid && sc.visible) {
      const popup = document.getElementById("floating-popup");
      const clampedX = Math.max(490, Math.min(window.innerWidth - 160, sc.x));
      const clampedY = Math.max(210, Math.min(window.innerHeight - 60, sc.y - 18));
      popup.style.left = `${clampedX}px`;
      popup.style.top = `${clampedY}px`;
    }
  }

  renderer.render(scene, camera);
}
animate();

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
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
    ):
        self.port = port
        self.master = SwarmMaster()
        self.joints: Dict[str, Dict[str, Any]] = {
            k: dict(v) for k, v in JOINT_CONFIG.items()
        }
        self.websockets = set()

        # Pre-register any explicit IP overrides passed via CLI flags
        if ip_overrides:
            for jid, ip_str in ip_overrides.items():
                if ip_str and jid in self.joints:
                    node_id = self.joints[jid]["node_id"]
                    self.master.connect(node_id, ip=ip_str)

        self.app = web.Application()
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/ws", self.handle_ws)
        self.app.on_cleanup.append(self._cleanup)

    def command_joint(self, joint_id: str, angle: int) -> bool:
        if joint_id not in self.joints:
            return False
        cfg = self.joints[joint_id]
        clamped = max(cfg["min_angle"], min(cfg["max_angle"], int(angle)))
        cfg["angle"] = clamped

        node = self.master.get(cfg["node_id"])
        if node is not None:
            node.servo("servo", clamped)
            return True
        return False

    def _build_status_payload(self) -> Dict[str, Any]:
        joints_out: Dict[str, Any] = {}
        for jid, cfg in self.joints.items():
            node = self.master.get(cfg["node_id"])
            online = bool(node is not None and node.is_online)
            joints_out[jid] = {
                **cfg,
                "online": online,
                "ip": f"{node.ip}:{node.port}" if node is not None else "--",
                "board": node.board if node is not None else "WAITING",
                "sensors": node.sensors if node is not None else {},
            }
        return {"joints": joints_out}

    async def handle_index(self, request: web.Request) -> web.Response:
        return web.Response(text=HTML_PAGE, content_type="text/html")

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
                        if isinstance(angle, (int, float)) and not isinstance(angle, bool):
                            self.command_joint(joint_id, int(angle))
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

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(self.telemetry_broadcast_loop())
        print("=" * 74)
        print("  OpenSwarm HydraArm Studio — 4-Controller Distributed Robotic Arm")
        print("=" * 74)
        print(f"  3D Interactive Studio URL : http://localhost:{self.port}")
        print("  Expected Slave Nodes on Wi-Fi (UDP 4210 / 4211):")
        for jid, cfg in self.joints.items():
            print(f"    - {cfg['label']:24s} -> {cfg['node_id']:20s} ({cfg['controller']}, {cfg['pin_label']})")
        print("=" * 74)
        web.run_app(self.app, host="127.0.0.1", port=self.port, loop=loop)


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenSwarm HydraArm 3D Interactive Studio")
    parser.add_argument("--port", type=int, default=8090, help="Local web server port (default: 8090)")
    parser.add_argument("--base-ip", type=str, default=None, help="Optional direct IP for arm_base_esp32")
    parser.add_argument("--shoulder-ip", type=str, default=None, help="Optional direct IP for arm_shoulder_unoq")
    parser.add_argument("--elbow-ip", type=str, default=None, help="Optional direct IP for arm_elbow_rp2040")
    parser.add_argument("--gripper-ip", type=str, default=None, help="Optional direct IP for arm_gripper_rpi")
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
