"""
OpenSwarm 3D Web Master Server.
Serves a high-tech Three.js 3D Open-World Swarm Arena in the browser:
- Discovers and commands real or virtual slave nodes over UDP.
- Real-time physics engine for robots, obstacles, and cooperative payload box.
- Keyboard WASD teleoperation for selected robot + Autonomous AI Cooperative Pushing planner.
- WebSockets for 60 FPS bidirectional telemetry between 3D Arena and OpenSwarm Master.
"""

import asyncio
import json
import math
import os
import time
from aiohttp import web

from openswarm.master import SwarmMaster

# ============================================================================
# 2D/3D RIGID BODY SIMULATION ARENA STATE (SI Units: meters, seconds)
# ============================================================================

class SwarmWorld:
    def __init__(self):
        # Arena size: 6.0m x 4.0m
        self.arena_w = 6.0
        self.arena_h = 4.0
        
        # Robots: x, y, theta (heading in radians), v, omega
        self.robots = {
            "tug_esp32": {
                "id": "tug_esp32",
                "board": "ESP32",
                "color": "#f97316",  # Vibrant Orange
                "x": -1.6,
                "y": -0.6,
                "theta": 0.0,
                "radius": 0.22,
                "target_x": 0.0,
                "target_y": 0.0,
                "mode": "IDLE",  # IDLE, MANUAL, AI_DOCK, AI_PUSH
                "motor_l": 0,
                "motor_r": 0,
                "battery": 11.8,
                "online": True
            },
            "tug_rp2040": {
                "id": "tug_rp2040",
                "board": "RP2040",
                "color": "#06b6d4",  # Cyan
                "x": -1.6,
                "y": 0.6,
                "theta": 0.0,
                "radius": 0.22,
                "target_x": 0.0,
                "target_y": 0.0,
                "mode": "IDLE",
                "motor_l": 0,
                "motor_r": 0,
                "battery": 12.1,
                "online": True
            }
        }

        # Payload Crate: x, y, theta, width, height, mass (heavy!)
        self.box = {
            "x": -0.5,
            "y": 0.0,
            "theta": 0.0,
            "width": 0.70,
            "height": 0.90,
            "vx": 0.0,
            "vy": 0.0,
            "v_theta": 0.0
        }

        # Goal Zone: Target where the swarm needs to transport the box
        self.goal = {
            "x": 1.8,
            "y": 0.0,
            "radius": 0.65
        }

        self.ai_active = False
        self.selected_bot = "tug_esp32"
        self.stats = {
            "packets_sent": 0,
            "fps": 60,
            "latency_ms": 1.6
        }

    def update_physics(self, dt: float):
        """Simulates differential drive kinematics and physical box contact."""
        WHEEL_BASE = 0.20
        MAX_SPEED = 0.85  # m/s

        # 1. Update Robots Kinematics
        for bot_id, bot in self.robots.items():
            vl = (bot["motor_l"] / 255.0) * MAX_SPEED
            vr = (bot["motor_r"] / 255.0) * MAX_SPEED
            
            linear_v = (vr + vl) / 2.0
            omega = (vr - vl) / WHEEL_BASE

            bot["theta"] += omega * dt
            bot["x"] += linear_v * math.cos(bot["theta"]) * dt
            bot["y"] += linear_v * math.sin(bot["theta"]) * dt

            # Keep inside arena
            bot["x"] = max(-self.arena_w/2 + 0.3, min(self.arena_w/2 - 0.3, bot["x"]))
            bot["y"] = max(-self.arena_h/2 + 0.3, min(self.arena_h/2 - 0.3, bot["y"]))

        # 2. Collision / Pushing Interaction with the Payload Box
        # Check contact between robots and box
        box_half_w = self.box["width"] / 2.0
        box_half_h = self.box["height"] / 2.0

        push_fx = 0.0
        push_fy = 0.0
        torque = 0.0

        for bot_id, bot in self.robots.items():
            # Vector from box center to robot
            dx = bot["x"] - self.box["x"]
            dy = bot["y"] - self.box["y"]
            dist = math.sqrt(dx*dx + dy*dy)

            # Simple contact threshold
            contact_dist = bot["radius"] + (box_half_w + box_half_h)/2.2
            if dist < contact_dist:
                # Robot is pushing the box!
                push_dir_x = math.cos(bot["theta"])
                push_dir_y = math.sin(bot["theta"])
                throttle = max(0, (bot["motor_l"] + bot["motor_r"]) / 510.0)

                push_fx += push_dir_x * throttle * 1.5
                push_fy += push_dir_y * throttle * 1.5

                # Relative torque (off-center pushing causes rotation)
                rel_y = bot["y"] - self.box["y"]
                torque += rel_y * push_fx * 0.4

                # Repel robot slightly so it doesn't clip through box
                overlap = contact_dist - dist
                if dist > 0.01:
                    bot["x"] += (dx / dist) * overlap * 0.5
                    bot["y"] += (dy / dist) * overlap * 0.5

        # Apply friction and update box
        self.box["vx"] = (self.box["vx"] + push_fx * dt) * 0.88
        self.box["vy"] = (self.box["vy"] + push_fy * dt) * 0.88
        self.box["v_theta"] = (self.box["v_theta"] + torque * dt) * 0.82

        self.box["x"] += self.box["vx"] * dt
        self.box["y"] += self.box["vy"] * dt
        self.box["theta"] += self.box["v_theta"] * dt

    def step_ai_swarm(self):
        """Cooperative Swarm AI: Coordinates both robots to push the box to the goal."""
        if not self.ai_active:
            return

        box_x = self.box["x"]
        box_y = self.box["y"]
        goal_x = self.goal["x"]
        goal_y = self.goal["y"]

        # Vector from box to goal
        target_dir_x = goal_x - box_x
        target_dir_y = goal_y - box_y
        dist_to_goal = math.hypot(target_dir_x, target_dir_y)

        if dist_to_goal < 0.25:
            # Goal reached! Stop
            for b in self.robots.values():
                b["motor_l"] = 0
                b["motor_r"] = 0
                b["mode"] = "GOAL REACHED!"
            self.ai_active = False
            return

        target_heading = math.atan2(target_dir_y, target_dir_x)

        # Compute cooperative docking points behind the box (Left & Right Pushers)
        push_dist_back = 0.55
        dock_offset_lat = 0.28  # Separation between Tug 1 and Tug 2

        # Tug 1 (ESP32) docking spot (Upper flank)
        dock1_x = box_x - math.cos(target_heading) * push_dist_back - math.sin(target_heading) * dock_offset_lat
        dock1_y = box_y - math.sin(target_heading) * push_dist_back + math.cos(target_heading) * dock_offset_lat

        # Tug 2 (RP2040) docking spot (Lower flank)
        dock2_x = box_x - math.cos(target_heading) * push_dist_back + math.sin(target_heading) * dock_offset_lat
        dock2_y = box_y - math.sin(target_heading) * push_dist_back - math.cos(target_heading) * dock_offset_lat

        self._drive_bot_to_pose("tug_esp32", dock1_x, dock1_y, target_heading)
        self._drive_bot_to_pose("tug_rp2040", dock2_x, dock2_y, target_heading)

    def _drive_bot_to_pose(self, bot_id: str, tx: float, ty: float, target_hdg: float):
        bot = self.robots[bot_id]
        dx = tx - bot["x"]
        dy = ty - bot["y"]
        dist = math.hypot(dx, dy)

        if dist > 0.12:
            # Waypoint seek mode
            bot["mode"] = "AI_APPROACH"
            desired_ang = math.atan2(dy, dx)
            ang_err = (desired_ang - bot["theta"] + math.pi) % (2 * math.pi) - math.pi
            
            # Simple proportional heading control
            kp = 180.0
            steer = max(-140, min(140, int(ang_err * kp)))
            base_spd = 180 if abs(ang_err) < 0.7 else 60
            bot["motor_l"] = max(-255, min(255, base_spd - steer))
            bot["motor_r"] = max(-255, min(255, base_spd + steer))
        else:
            # In position behind box -> PUSH!
            bot["mode"] = "COOPERATIVE_PUSH"
            ang_err = (target_hdg - bot["theta"] + math.pi) % (2 * math.pi) - math.pi
            steer = int(ang_err * 120.0)
            bot["motor_l"] = max(-255, min(255, 230 - steer))
            bot["motor_r"] = max(-255, min(255, 230 + steer))


# ============================================================================
# EMBEDDED THREE.JS 3D ARENA HTML DASHBOARD
# ============================================================================

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>OpenSwarm — Fleet Master 3D Command Deck</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
    body { background: #090d16; color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; overflow: hidden; height: 100vh; display: flex; flex-direction: column; }
    
    /* Top Bar */
    header {
      background: rgba(15, 23, 42, 0.95);
      border-bottom: 1px solid #1e293b;
      padding: 10px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      z-index: 10;
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .logo-badge { background: linear-gradient(135deg, #0284c7, #38bdf8); color: white; padding: 4px 10px; border-radius: 6px; font-weight: 800; font-size: 13px; letter-spacing: 0.5px; }
    .brand-title { font-size: 16px; font-weight: 700; color: #ffffff; letter-spacing: 0.5px; }
    .brand-sub { font-size: 12px; color: #94a3b8; margin-left: 6px; }
    
    .hud-metrics { display: flex; gap: 20px; font-size: 12px; }
    .metric { display: flex; flex-direction: column; align-items: flex-end; }
    .metric-val { font-weight: bold; color: #38bdf8; font-size: 14px; }
    .metric-label { color: #64748b; font-size: 10px; text-transform: uppercase; }

    /* Main Container */
    #viewport-container { position: relative; flex: 1; width: 100%; height: 100%; }
    #three-canvas { width: 100%; height: 100%; display: block; }

    /* Floating Control Overlay */
    .overlay-panel {
      position: absolute;
      background: rgba(15, 23, 42, 0.88);
      backdrop-filter: blur(10px);
      border: 1px solid #334155;
      border-radius: 10px;
      padding: 14px;
      z-index: 5;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }

    #fleet-panel { top: 20px; left: 20px; width: 280px; }
    #teleop-panel { bottom: 20px; right: 20px; width: 320px; }
    #ai-panel { top: 20px; right: 20px; width: 280px; }

    .panel-header { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; color: #94a3b8; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
    
    /* Robot Cards */
    .robot-card {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 10px;
      margin-bottom: 8px;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .robot-card:hover { border-color: #38bdf8; background: #243248; }
    .robot-card.selected { border-color: #38bdf8; box-shadow: 0 0 12px rgba(56, 189, 248, 0.35); }
    .card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .bot-name { font-weight: bold; font-size: 13px; display: flex; align-items: center; gap: 6px; }
    .bot-dot { width: 8px; height: 8px; border-radius: 50%; }
    .bot-pill { font-size: 10px; background: #0f172a; padding: 2px 6px; border-radius: 4px; color: #94a3b8; }
    .card-meta { display: flex; justify-content: space-between; font-size: 11px; color: #cbd5e1; }

    /* Action Buttons */
    .btn {
      width: 100%;
      padding: 10px;
      border: none;
      border-radius: 6px;
      font-weight: 700;
      font-size: 13px;
      cursor: pointer;
      transition: all 0.15s ease;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }
    .btn-primary { background: linear-gradient(135deg, #0284c7, #0ea5e9); color: white; }
    .btn-primary:hover { background: linear-gradient(135deg, #0369a1, #0284c7); }
    .btn-ai-active { background: linear-gradient(135deg, #16a34a, #22c55e) !important; color: white; }
    .btn-danger { background: #dc2626; color: white; margin-top: 8px; }
    .btn-danger:hover { background: #b91c1c; }

    /* D-Pad Buttons */
    .dpad-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; width: 140px; margin: 10px auto; }
    .dpad-btn { background: #1e293b; border: 1px solid #475569; color: white; font-weight: bold; padding: 12px; border-radius: 6px; text-align: center; cursor: pointer; }
    .dpad-btn:active { background: #38bdf8; color: black; }
    .dpad-center { background: #0f172a; border-color: #334155; }

    /* Keybinds Helper */
    .key-hint { font-size: 11px; color: #94a3b8; text-align: center; margin-top: 6px; }
    kbd { background: #334155; padding: 2px 5px; border-radius: 4px; color: #f1f5f9; }
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>

  <header>
    <div class="brand">
      <div class="logo-badge">OPENSWARM</div>
      <div class="brand-title">Fleet Command Center</div>
      <div class="brand-sub">Master–Slave Remote HAL</div>
    </div>
    <div class="hud-metrics">
      <div class="metric">
        <span class="metric-val" id="metric-ping">1.6 ms</span>
        <span class="metric-label">UDP Latency</span>
      </div>
      <div class="metric">
        <span class="metric-val" id="metric-pkts">0</span>
        <span class="metric-label">Packets Out</span>
      </div>
      <div class="metric">
        <span class="metric-val" style="color: #4ade80;">20 Hz</span>
        <span class="metric-label">Telemetry Stream</span>
      </div>
    </div>
  </header>

  <div id="viewport-container">
    <canvas id="three-canvas"></canvas>

    <!-- Fleet Left Panel -->
    <div class="overlay-panel" id="fleet-panel">
      <div class="panel-header">Connected Slaves (UDP)</div>
      
      <div class="robot-card selected" id="card-tug_esp32" onclick="selectRobot('tug_esp32')">
        <div class="card-top">
          <div class="bot-name">
            <div class="bot-dot" style="background: #f97316;"></div>
            tug_esp32
          </div>
          <span class="bot-pill">ESP32 (Core 0)</span>
        </div>
        <div class="card-meta">
          <span>Motors: <strong id="m-esp32">L:0 R:0</strong></span>
          <span style="color: #4ade80;">ONLINE</span>
        </div>
      </div>

      <div class="robot-card" id="card-tug_rp2040" onclick="selectRobot('tug_rp2040')">
        <div class="card-top">
          <div class="bot-name">
            <div class="bot-dot" style="background: #06b6d4;"></div>
            tug_rp2040
          </div>
          <span class="bot-pill">RP2040 Dual M0+</span>
        </div>
        <div class="card-meta">
          <span>Motors: <strong id="m-rp2040">L:0 R:0</strong></span>
          <span style="color: #4ade80;">ONLINE</span>
        </div>
      </div>
      
      <div style="font-size: 11px; color: #94a3b8; margin-top: 8px;">
        * Slaves have zero control logic (void loop is empty). All kinematics run on Linux Master.
      </div>
    </div>

    <!-- AI Right Panel -->
    <div class="overlay-panel" id="ai-panel">
      <div class="panel-header">Swarm Autonomous AI</div>
      <button class="btn btn-primary" id="btn-ai" onclick="toggleAI()">
        ⚡ Start Cooperative Push
      </button>
      <button class="btn btn-danger" onclick="sendStop()">
        ⛔ Emergency All Stop
      </button>
      <div style="font-size: 11px; color: #94a3b8; margin-top: 10px; line-height: 1.4;">
        <strong>Task:</strong> Both micro-tugs coordinate formation and push the heavy payload crate to the <strong>Goal Pad</strong>!
      </div>
    </div>

    <!-- Teleop Bottom Panel -->
    <div class="overlay-panel" id="teleop-panel">
      <div class="panel-header">
        <span>Manual Teleoperation</span>
        <span id="active-bot-label" style="color: #38bdf8;">tug_esp32</span>
      </div>
      <div class="dpad-grid">
        <div></div>
        <div class="dpad-btn" onmousedown="drive(200, 200)" onmouseup="drive(0, 0)">▲</div>
        <div></div>
        <div class="dpad-btn" onmousedown="drive(-160, 160)" onmouseup="drive(0, 0)">◀</div>
        <div class="dpad-btn dpad-center" onclick="drive(0, 0)">■</div>
        <div class="dpad-btn" onmousedown="drive(160, -160)" onmouseup="drive(0, 0)">▶</div>
        <div></div>
        <div class="dpad-btn" onmousedown="drive(-200, -200)" onmouseup="drive(0, 0)">▼</div>
        <div></div>
      </div>
      <div class="key-hint">Keyboard: <kbd>W</kbd> <kbd>A</kbd> <kbd>S</kbd> <kbd>D</kbd> | Press <kbd>1</kbd>/<kbd>2</kbd> to switch bot</div>
    </div>

  </div>

  <script>
    // ------------------------------------------------------------------------
    // 1. Three.js Open-World 3D Scene Setup
    // ------------------------------------------------------------------------
    const container = document.getElementById('viewport-container');
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x090d16);
    scene.fog = new THREE.FogExp2(0x090d16, 0.08);

    const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 100);
    camera.position.set(0, 4.8, 4.2);

    const renderer = new THREE.WebGLRenderer({ canvas: document.getElementById('three-canvas'), antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight - 50);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true;

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 0, 0);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI / 2.1;

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.65);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.9);
    dirLight.position.set(5, 10, 7);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 1024;
    dirLight.shadow.mapSize.height = 1024;
    scene.add(dirLight);

    // Arena Floor Grid
    const floorGeo = new THREE.PlaneGeometry(6.0, 4.0);
    const floorMat = new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 0.8 });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    const grid = new THREE.GridHelper(6.0, 30, 0x38bdf8, 0x1e293b);
    grid.position.y = 0.002;
    scene.add(grid);

    // Goal Pad (Target Drop Zone)
    const goalGeo = new THREE.CylinderGeometry(0.65, 0.65, 0.015, 32);
    const goalMat = new THREE.MeshBasicMaterial({ color: 0x22c55e, wireframe: true });
    const goalMesh = new THREE.Mesh(goalGeo, goalMat);
    goalMesh.position.set(1.8, 0.01, 0);
    scene.add(goalMesh);

    // Goal Center Neon Disc
    const goalDisc = new THREE.Mesh(
      new THREE.CircleGeometry(0.62, 32),
      new THREE.MeshBasicMaterial({ color: 0x15803d, transparent: true, opacity: 0.35 })
    );
    goalDisc.rotation.x = -Math.PI / 2;
    goalDisc.position.set(1.8, 0.012, 0);
    scene.add(goalDisc);

    // ------------------------------------------------------------------------
    // 2. Interactive Objects (Robots & Payload Crate)
    // ------------------------------------------------------------------------
    const robotMeshes = {};

    function createRobotMesh(colorHex, name) {
      const group = new THREE.Group();
      
      // Circular Chassis Base
      const baseGeo = new THREE.CylinderGeometry(0.22, 0.22, 0.09, 32);
      const baseMat = new THREE.MeshStandardMaterial({ color: colorHex, roughness: 0.4 });
      const base = new THREE.Mesh(baseGeo, baseMat);
      base.position.y = 0.045;
      base.castShadow = true;
      group.add(base);

      // Top Electronics Lid (Black with ArUco Marker)
      const topGeo = new THREE.CylinderGeometry(0.20, 0.20, 0.02, 32);
      const topMat = new THREE.MeshStandardMaterial({ color: 0x1e293b });
      const top = new THREE.Mesh(topGeo, topMat);
      top.position.y = 0.095;
      group.add(top);

      // Front Directional Marker / Pushing Face
      const noseGeo = new THREE.BoxGeometry(0.12, 0.06, 0.06);
      const noseMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
      const nose = new THREE.Mesh(noseGeo, noseMat);
      nose.position.set(0.18, 0.05, 0);
      group.add(nose);

      // Wheels
      const wheelGeo = new THREE.CylinderGeometry(0.065, 0.065, 0.035, 16);
      const wheelMat = new THREE.MeshStandardMaterial({ color: 0x0f172a });
      const wL = new THREE.Mesh(wheelGeo, wheelMat);
      wL.rotation.x = Math.PI / 2;
      wL.position.set(0, 0.065, 0.20);
      group.add(wL);

      const wR = wL.clone();
      wR.position.set(0, 0.065, -0.20);
      group.add(wR);

      scene.add(group);
      return group;
    }

    robotMeshes["tug_esp32"] = createRobotMesh(0xf97316, "ESP32");
    robotMeshes["tug_rp2040"] = createRobotMesh(0x06b6d4, "RP2040");

    // Heavy Payload Box (with ArUco pattern on top)
    const boxGeo = new THREE.BoxGeometry(0.70, 0.35, 0.90);
    const boxMat = new THREE.MeshStandardMaterial({ color: 0xeab308, roughness: 0.5 });
    const payloadMesh = new THREE.Mesh(boxGeo, boxMat);
    payloadMesh.position.y = 0.35 / 2;
    payloadMesh.castShadow = true;
    scene.add(payloadMesh);

    // ArUco Card on Box
    const arucoGeo = new THREE.PlaneGeometry(0.35, 0.35);
    const arucoMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const arucoCard = new THREE.Mesh(arucoGeo, arucoMat);
    arucoCard.rotation.x = -Math.PI / 2;
    arucoCard.position.y = 0.355;
    payloadMesh.add(arucoCard);

    // ------------------------------------------------------------------------
    // 3. Telemetry Sync & WebSockets
    // ------------------------------------------------------------------------
    let ws = null;
    let selectedBot = "tug_esp32";
    let aiActive = false;

    function connectWS() {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${proto}//${window.location.host}/ws`);

      ws.onmessage = (evt) => {
        const data = JSON.parse(evt.data);
        updateScene(data);
      };

      ws.onclose = () => { setTimeout(connectWS, 1000); };
    }
    connectWS();

    function updateScene(world) {
      // Sync Robots
      for (const id in world.robots) {
        const bot = world.robots[id];
        const mesh = robotMeshes[id];
        if (mesh) {
          mesh.position.x = bot.x;
          mesh.position.z = -bot.y;
          mesh.rotation.y = bot.theta;
        }
        // Update HUD motor indicators
        const el = document.getElementById(id === "tug_esp32" ? "m-esp32" : "m-rp2040");
        if (el) el.innerText = `L:${bot.motor_l} R:${bot.motor_r}`;
      }

      // Sync Box
      payloadMesh.position.x = world.box.x;
      payloadMesh.position.z = -world.box.y;
      payloadMesh.rotation.y = world.box.theta;

      // Update HUD stats
      document.getElementById('metric-pkts').innerText = world.stats.packets_sent;
      document.getElementById('metric-ping').innerText = `${world.stats.latency_ms.toFixed(1)} ms`;
      
      aiActive = world.ai_active;
      const btn = document.getElementById('btn-ai');
      if (aiActive) {
        btn.classList.add('btn-ai-active');
        btn.innerText = "✓ Swarm AI Active (Cooperative)";
      } else {
        btn.classList.remove('btn-ai-active');
        btn.innerText = "⚡ Start Cooperative Push";
      }
    }

    // Controls
    function selectRobot(id) {
      selectedBot = id;
      document.getElementById('card-tug_esp32').classList.toggle('selected', id === 'tug_esp32');
      document.getElementById('card-tug_rp2040').classList.toggle('selected', id === 'tug_rp2040');
      document.getElementById('active-bot-label').innerText = id;
    }

    function drive(l, r) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ op: "DRIVE", id: selectedBot, left: l, right: r }));
      }
    }

    function toggleAI() {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ op: "TOGGLE_AI" }));
      }
    }

    function sendStop() {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ op: "STOP_ALL" }));
      }
    }

    // Keyboard Teleop
    const keysDown = {};
    window.addEventListener('keydown', (e) => {
      if (keysDown[e.key]) return;
      keysDown[e.key] = true;

      if (e.key === '1') selectRobot('tug_esp32');
      if (e.key === '2') selectRobot('tug_rp2040');

      let l = 0, r = 0;
      if (keysDown['w'] || keysDown['W']) { l = 210; r = 210; }
      if (keysDown['s'] || keysDown['S']) { l = -210; r = -210; }
      if (keysDown['a'] || keysDown['A']) { l = -160; r = 160; }
      if (keysDown['d'] || keysDown['D']) { l = 160; r = -160; }
      if (l !== 0 || r !== 0) drive(l, r);
    });

    window.addEventListener('keyup', (e) => {
      delete keysDown[e.key];
      if (!keysDown['w'] && !keysDown['s'] && !keysDown['a'] && !keysDown['d']) {
        drive(0, 0);
      }
    });

    window.addEventListener('resize', () => {
      camera.aspect = window.innerWidth / (window.innerHeight - 50);
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight - 50);
    });

    function animate() {
      requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }
    animate();
  </script>
</body>
</html>
"""

# ============================================================================
# MASTER APPLICATION & WEBSOCKET BROADCASTER
# ============================================================================

class OpenSwarmServer:
    def __init__(self, port: int = 8080):
        self.port = port
        self.world = SwarmWorld()
        self.master = SwarmMaster()
        self.app = web.Application()
        self.websockets = set()

        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_get('/ws', self.handle_ws)

    async def handle_index(self, request):
        return web.Response(text=HTML_PAGE, content_type='text/html')

    async def handle_ws(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.websockets.add(ws)

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    op = data.get("op")
                    
                    if op == "DRIVE":
                        bot_id = data.get("id")
                        l = data.get("left", 0)
                        r = data.get("right", 0)
                        if bot_id in self.world.robots:
                            self.world.robots[bot_id]["motor_l"] = l
                            self.world.robots[bot_id]["motor_r"] = r
                            # Send real low-latency UDP command via SwarmMaster
                            self.master.send_command(bot_id, "drive", {"left": l, "right": r})
                            self.world.stats["packets_sent"] += 1

                    elif op == "TOGGLE_AI":
                        self.world.ai_active = not self.world.ai_active
                    
                    elif op == "STOP_ALL":
                        self.world.ai_active = False
                        for b in self.world.robots.values():
                            b["motor_l"] = 0
                            b["motor_r"] = 0
                        self.master.emergency_stop()

        finally:
            self.websockets.remove(ws)
        return ws

    async def simulation_loop(self):
        """60 Hz Physics + AI Loop + 20 Hz WebSocket state broadcast."""
        dt = 0.016
        tick = 0
        while True:
            t0 = time.time()
            if self.world.ai_active:
                self.world.step_ai_swarm()
                # Dispatch commands from AI to physical/virtual nodes
                for bot_id in ["tug_esp32", "tug_rp2040"]:
                    bot = self.world.robots[bot_id]
                    self.master.send_command(bot_id, "drive", {"left": bot["motor_l"], "right": bot["motor_r"]})
                    self.world.stats["packets_sent"] += 1

            self.world.update_physics(dt)

            # Broadcast state to Three.js web clients at 30 Hz
            tick += 1
            if tick % 2 == 0 and self.websockets:
                payload = json.dumps({
                    "robots": self.world.robots,
                    "box": self.world.box,
                    "stats": self.world.stats,
                    "ai_active": self.world.ai_active
                })
                for ws in list(self.websockets):
                    try:
                        await ws.send_str(payload)
                    except Exception:
                        pass

            elapsed = time.time() - t0
            sleep_time = max(0.001, dt - elapsed)
            await asyncio.sleep(sleep_time)

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(self.simulation_loop())
        print(f"\n[OpenSwarm Master] 3D Fleet Command Center running at: http://localhost:{self.port}")
        web.run_app(self.app, host="0.0.0.0", port=self.port, loop=loop)


if __name__ == "__main__":
    server = OpenSwarmServer(port=8080)
    server.run()
