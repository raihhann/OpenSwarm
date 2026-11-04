# OpenSwarm — Distributed Hardware-Agnostic Robotics Framework

**OpenSwarm** is a Klipper-inspired, **Zero-Control-Logic Distributed Hardware Abstraction Layer (Remote HAL)** and fleet orchestration framework for heterogeneous multi-robot systems.

### Core Architectural Rule
> **Slaves contain 0% control logic.**  
> Whether a Slave is an 8-bit Arduino UNO, a 32-bit ESP32/RP2040, or a Linux SBC (Raspberry Pi, Portenta X8, Arduino UNO Q), the Slave **only declares its network connection, Node ID, and attached sensor/actuator pins**. `void loop()` is 100% empty.  
> **100% of closed-loop control, kinematics, vision, and multi-robot coordination runs on the Linux Master.**

---

## Repository Structure

```text
OpenSwarm/
├── slaves/
│   ├── arduino/
│   │   └── SwarmNode/          # C++ Arduino Slave Library (ESP32, UNO, Nano, RP2040)
│   └── linux/                  # Python/Linux Slave Agent (Arduino UNO Q, Portenta X8, Raspberry Pi)
├── master/                     # Central Linux Master SDK, Auto-Discovery & Control Runtime
└── examples/
    └── ant_colony_tugs/        # Flagship Demo: Cooperative Heavy-Object Manipulation Swarm
```

---

## Installing the Arduino Library (`SwarmNode`)

### Method 1: Download from the `SwarmNode` GitHub Branch (Recommended)
1. Switch to the **`SwarmNode`** branch on GitHub.
2. Click **Code -> Download ZIP**.
3. In Arduino IDE, go to **Sketch -> Include Library -> Add .ZIP Library...** and select the downloaded `.zip`.
4. Include it in your sketch with `#include <SwarmNode.h>` (or `#include <OpenSwarm.h>`).

### Method 2: Sync `slaves/arduino/SwarmNode` to the `SwarmNode` Branch
Whenever you update files inside `slaves/arduino/SwarmNode/`, update and push the standalone `SwarmNode` branch:
```powershell
$tree = git rev-parse HEAD:slaves/arduino/SwarmNode
$commit = git commit-tree $tree -m "release(arduino): sync SwarmNode Arduino library"
git branch -f SwarmNode $commit
git push origin main SwarmNode --force
```

---

## Slave Roadmap
- [x] **Step 1:** ESP32 Slave Library (`hal_esp32.h` — Full Actuator & Sensor Suite)
- [ ] **Step 2:** Arduino UNO Slave Support (`hal_uno.h`)
- [ ] **Step 3:** Arduino Nano Slave Support (`hal_nano.h`)
- [ ] **Step 4:** RP2040 Slave Support (`hal_rp2040.h`)
- [ ] **Step 5:** Linux Slave Package (`slaves/linux/` for Arduino UNO Q, Portenta X8, Raspberry Pi)
- [ ] **Step 6:** Central Linux Master (`master/`) & Ant-Colony Micro-Tugs (`examples/ant_colony_tugs/`)
