# OpenSwarm HydraArm — Multi-Controller Distributed Robotic Arm

**HydraArm** turns the 3D-printed [**Servo Mini Arm (by Luca Dilo)**](https://makerworld.com/en/models/1290483-servo-mini-arm) into a showcase for **OpenSwarm's Heterogeneous Remote HAL**:
* The 4 servo motors are distributed across **3 different controller architectures** over Wi-Fi (`1× ESP32 + 1× RP2040 + 1× Raspberry Pi Ubuntu 24.04`).
* Every Slave runs **0% control logic** (`void loop()` is 100% empty on all microcontrollers).
* Your **Linux PC Master** coordinates all joints simultaneously through an interactive **3D Digital Twin Web Studio** (where you click any servo motor on the 3D arm and drag its popup slider to move the real robot) or an interactive **Terminal CLI**.

---

## 1. Which Servo Connects Where (Complete Wiring Guide)

Each SG90 / MG90S servo has 3 wires:
* **Orange / Yellow** = PWM Signal
* **Red** = `+5V` Power (`VBUS` / `VIN` / `5V`)
* **Brown / Black** = `GND` *(Must share common GND with the controller!)*

| Joint on the Arm | Role | Controller | Slave Node ID | Actuator Name | Signal Pin | Power (`+5V`) | Ground (`GND`) | Firmware / Script |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Joint 1: Base Yaw** | Rotates circular base left/right (`0°–180°`, Home `90°`) | **ESP32** | `arm_base_esp32` | `servo` | **GPIO 13** (`D13`) | `5V` / `VIN` | `GND` | [`esp32_base_node.ino`](./slaves/esp32_base_node/esp32_base_node.ino) |
| **Joint 2: Shoulder Pitch** | Tilts black twin vertical link (`20°–160°`, Home `140°`) | **Raspberry Pi** *(Ubuntu 24.04)* | `arm_shoulder_gripper_rpi` | `shoulder_servo` | **BCM GPIO 14** *(Physical Pin 8)* | **Physical Pin 2** (`5V`) | **Physical Pin 6** (`GND`) | [`rpi_shoulder_gripper_node.py`](./slaves/rpi_shoulder_gripper_node/rpi_shoulder_gripper_node.py) |
| **Joint 3: Elbow Pitch** | Raises/lowers grey forearm link (`20°–160°`, Home `90°`) | **RP2040** *(Nano RP2040 / Pico W)* | `arm_elbow_rp2040` | `servo` | **Pin 6** (`D6` / `GP6`) | `VUSB` / `VBUS` (`5V`) | `GND` | [`rp2040_elbow_node.ino`](./slaves/rp2040_elbow_node/rp2040_elbow_node.ino) |
| **Joint 4: Gripper Claw** | Opens/closes geared black jaws (`10°–95°`, Home `45°`) | **Raspberry Pi** *(Ubuntu 24.04)* | `arm_shoulder_gripper_rpi` | `gripper_servo` | **BCM GPIO 18** *(Physical Pin 12)* | **Physical Pin 4** (`5V`) | **Physical Pin 14** (`GND`) | [`rpi_shoulder_gripper_node.py`](./slaves/rpi_shoulder_gripper_node/rpi_shoulder_gripper_node.py) |

### Raspberry Pi 40-Pin Header Quick Map (Outer Even Pin Row)
Both Raspberry Pi servos wire cleanly to the **outer edge (even-numbered pins)** of the Raspberry Pi header:
* **Pin 2 (`5V`)** -> Shoulder Servo Red (`+5V`)
* **Pin 4 (`5V`)** -> Gripper Servo Red (`+5V`)
* **Pin 6 (`GND`)** -> Shoulder Servo Brown/Black (`GND`)
* **Pin 8 (`BCM GPIO 14`)** -> Shoulder Servo Orange/Yellow (`Signal`)
* **Pin 12 (`BCM GPIO 18`)** -> Gripper Servo Orange/Yellow (`Signal`)
* **Pin 14 (`GND`)** -> Gripper Servo Brown/Black (`GND`)

---

## 2. Setting Up Each Slave Controller

### A. Joint 1 — ESP32 (`arm_base_esp32`)
1. Open [`slaves/esp32_base_node/esp32_base_node.ino`](./slaves/esp32_base_node/esp32_base_node.ino) in Arduino IDE.
2. Set your `WIFI_SSID` and `WIFI_PASS` and upload to the ESP32.
3. Connect the **Base Yaw Servo** signal wire to **GPIO 13**.

### B. Joint 3 — RP2040 (`arm_elbow_rp2040`)
1. Open [`slaves/rp2040_elbow_node/rp2040_elbow_node.ino`](./slaves/rp2040_elbow_node/rp2040_elbow_node.ino) in Arduino IDE, set your `WIFI_SSID` and `WIFI_PASS`, and upload to your RP2040 board.
2. Connect the **Elbow Pitch Servo** signal wire to **Pin 6 (`D6` / `GP6`)**.

### C. Joint 2 (Shoulder) & Joint 4 (Gripper) — Raspberry Pi Ubuntu 24.04 (`arm_shoulder_gripper_rpi`)
SSH into your Raspberry Pi running **Ubuntu 24.04 LTS Server** and run:
```bash
# 1. Install Ubuntu 24.04 GPIO packages & openswarm-slave
sudo apt update
sudo apt install -y python3 python3-pip python3-lgpio python3-rpi-lgpio python3-smbus2 python3-serial git
sudo python3 -m pip install --break-system-packages --upgrade openswarm-slave

# 2. Pull the repo and start the Dual-Servo Raspberry Pi Slave node
cd ~/OpenSwarm
git pull
cd projects/hydra_arm/slaves/rpi_shoulder_gripper_node
sudo python3 rpi_shoulder_gripper_node.py
```

---

## 3. Running HydraArm on Your Linux Master PC

First, make sure `openswarm-master` and `aiohttp` (for the 3D Web Studio) are installed on your Linux PC:
```bash
pip install -e "master[demo]"
```

### Option A: Interactive 3D Digital Twin Studio (Click Any Motor -> Slider Appears!)
```bash
python3 projects/hydra_arm/master/hydra_arm_studio.py
```
Then open **`http://localhost:8090`** in your browser:
* **Click directly on any of the 4 blue SG90 servos** on the 3D arm (or its floating label).
* A **floating joint slider popup** appears right over that motor.
* Dragging the slider moves the 3D arm AND sends real-time UDP servo commands to that joint's controller (`ESP32`, `RP2040`, or `Raspberry Pi`)!

*(Tip: To test the 3D Studio on your PC before powering on the boards, run `python3 projects/hydra_arm/master/virtual_arm_slaves.py` in another terminal!)*

### Option B: Interactive Terminal CLI
```bash
python3 projects/hydra_arm/master/hydra_arm_cli.py
```
Example terminal commands:
```text
hydra> status
hydra> base 120
hydra> shoulder 140
hydra> elbow 75
hydra> gripper 20
hydra> pose 90 125 65 85
hydra> home
hydra> demo
```
