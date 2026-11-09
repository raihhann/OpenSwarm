# OpenSwarm HydraArm — 4-Controller Distributed Robotic Arm

**HydraArm** turns the 3D-printed [**Servo Mini Arm (by Luca Dilo)**](https://makerworld.com/en/models/1290483-servo-mini-arm) into a flagship showcase for **OpenSwarm's Heterogeneous Remote HAL**:
* Every single joint of the 4-DOF arm is wired to a **completely different controller architecture** across Wi-Fi (`1× ESP32 + 1× Arduino UNO Q + 1× RP2040 + 1× Raspberry Pi Ubuntu 24.04`).
* Every Slave runs **0% control logic** (`void loop()` is 100% empty on all microcontrollers).
* Your **Linux PC Master** coordinates all 4 controllers simultaneously through an interactive **3D Digital Twin Web Studio** (where you click any servo motor on the 3D arm and drag its popup slider to move the real robot) or an interactive **Terminal CLI**.

---

## 1. Which Servo Connects Where (Complete Wiring Guide)

Each SG90 / MG90S servo has 3 wires:
* **Orange / Yellow** = PWM Signal
* **Red** = `+5V` Power (`VBUS` / `VIN` / `5V`)
* **Brown / Black** = `GND` *(Must share common GND with the controller!)*

| Joint on the Arm | Role | Controller | Slave Node ID | Signal Pin | Power (`+5V`) | Ground (`GND`) | Firmware / Script |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Joint 1: Base Yaw** | Rotates circular base left/right (`0°–180°`) | **ESP32** | `arm_base_esp32` | **GPIO 13** (`D13`) | `5V` / `VIN` | `GND` | [`esp32_base_node.ino`](./slaves/esp32_base_node/esp32_base_node.ino) |
| **Joint 2: Shoulder Pitch** | Tilts black twin vertical link (`20°–160°`) | **Arduino UNO Q** | `arm_shoulder_unoq` | **Digital Pin 9** (`D9`) | `5V` | `GND` | [`unoq_mcu_bridge.ino`](./slaves/unoq_shoulder_node/unoq_mcu_bridge/unoq_mcu_bridge.ino) + [`unoq_shoulder_node.py`](./slaves/unoq_shoulder_node/unoq_shoulder_node.py) |
| **Joint 3: Elbow Pitch** | Raises/lowers grey forearm link (`20°–160°`) | **RP2040** *(Nano RP2040 / Pico W)* | `arm_elbow_rp2040` | **Pin 6** (`D6` / `GP6`) | `VUSB` / `VBUS` (`5V`) | `GND` | [`rp2040_elbow_node.ino`](./slaves/rp2040_elbow_node/rp2040_elbow_node.ino) |
| **Joint 4: Gripper Claw** | Opens/closes geared black jaws (`10°–95°`) | **Raspberry Pi** *(Ubuntu 24.04)* | `arm_gripper_rpi` | **BCM GPIO 18** *(Physical Pin 12)* | **Physical Pin 2 or 4** (`5V`) | **Physical Pin 6** (`GND`) | [`rpi_gripper_node.py`](./slaves/rpi_gripper_node/rpi_gripper_node.py) |

---

## 2. Setting Up Each of the 4 Slave Controllers

### A. Joint 1 — ESP32 (`arm_base_esp32`)
1. Update your local Arduino IDE `SwarmNode` library and open [`slaves/esp32_base_node/esp32_base_node.ino`](./slaves/esp32_base_node/esp32_base_node.ino).
2. Set your `WIFI_SSID` and `WIFI_PASS` and upload to the ESP32.
3. Connect the **Base Yaw Servo** signal wire to **GPIO 13**.

### B. Joint 2 — Arduino UNO Q (`arm_shoulder_unoq`)
Because the **Arduino UNO Q** has a dual-brain architecture (an **STM32U585 MCU** driving the `D0–D13` header pins + a **Qualcomm DragonWing QRB2210 Linux MPU** with Wi-Fi and Python):
1. **Flash the STM32 MCU side:** Open [`slaves/unoq_shoulder_node/unoq_mcu_bridge/unoq_mcu_bridge.ino`](./slaves/unoq_shoulder_node/unoq_mcu_bridge/unoq_mcu_bridge.ino) in Arduino IDE / Arduino App Lab and upload it to the UNO Q. It attaches the shoulder servo on **Pin D9** and exposes `set_servo` to the Linux side via `<Arduino_RouterBridge.h>` (`void loop()` is 100% empty!).
2. **Run the Linux Slave on the UNO Q:** SSH into (or open the terminal on) the Arduino UNO Q's Debian Linux side:
   ```bash
   git clone https://github.com/raihhann/OpenSwarm.git
   cd OpenSwarm/projects/hydra_arm/slaves/unoq_shoulder_node
   python3 unoq_shoulder_node.py
   ```
3. Connect the **Shoulder Pitch Servo** signal wire to **Digital Pin 9 (`D9`)**, power to `5V`, and ground to `GND`.

### C. Joint 3 — RP2040 (`arm_elbow_rp2040`)
1. Open [`slaves/rp2040_elbow_node/rp2040_elbow_node.ino`](./slaves/rp2040_elbow_node/rp2040_elbow_node.ino) in Arduino IDE, set your `WIFI_SSID` and `WIFI_PASS`, and upload to your RP2040 board.
2. Connect the **Elbow Pitch Servo** signal wire to **Pin 6 (`D6` / `GP6`)**.

### D. Joint 4 — Raspberry Pi Ubuntu 24.04 Server (`arm_gripper_rpi`)
SSH into your Raspberry Pi running **Ubuntu 24.04 LTS Server** and run:
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-lgpio python3-rpi-lgpio python3-smbus2 python3-serial git
sudo python3 -m pip install --break-system-packages --upgrade openswarm-slave

git clone https://github.com/raihhann/OpenSwarm.git
cd OpenSwarm/projects/hydra_arm/slaves/rpi_gripper_node
sudo python3 rpi_gripper_node.py
```
Connect the **Gripper Servo** signal wire to **BCM GPIO 18 (Physical Pin 12)**, `+5V` to **Physical Pin 2 or 4**, and `GND` to **Physical Pin 6**.

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
* Dragging the slider moves the 3D arm AND sends real-time UDP servo commands to that joint's controller (`ESP32`, `Arduino UNO Q`, `RP2040`, or `Raspberry Pi`)!

*(Tip: To test the 3D Studio on your PC before powering on the boards, run `python3 projects/hydra_arm/master/virtual_arm_slaves.py` in another terminal!)*

### Option B: Interactive Terminal CLI
```bash
python3 projects/hydra_arm/master/hydra_arm_cli.py
```
Example terminal commands:
```text
hydra> status
hydra> base 120
hydra> shoulder 110
hydra> elbow 75
hydra> gripper 20
hydra> pose 90 125 65 85
hydra> home
hydra> demo
```
