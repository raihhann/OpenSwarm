# OpenSwarm HydraArm — 4-Controller Distributed Robotic Arm

**HydraArm** turns the 3D-printed [**Servo Mini Arm (by Luca Dilo)**](https://makerworld.com/en/models/1290483-servo-mini-arm) into a showcase for **OpenSwarm's Heterogeneous Remote HAL**:
* Every single joint of the 4-DOF arm is wired to a **different microcontroller / SBC** across Wi-Fi (`2× ESP32 + 1× RP2040 + 1× Raspberry Pi Ubuntu 24.04`).
* Every Slave runs **0% control logic** (`void loop()` is 100% empty on the microcontrollers).
* Your **Linux PC Master** coordinates all 4 controllers simultaneously through an interactive **3D Digital Twin Web Studio** (where you click any servo motor on the 3D arm and drag its popup slider to move the real robot) or an interactive **Terminal CLI**.

---

## 1. Which Servo Connects Where (Complete Wiring Guide)

Each SG90 / MG90S servo has 3 wires:
* **Orange / Yellow** = PWM Signal
* **Red** = `+5V` Power (`VBUS` / `VIN` / `5V`)
* **Brown / Black** = `GND` *(Must share common GND with the controller!)*

| Joint on the Arm | Role | Controller | Slave Node ID | Signal Pin | Power (`+5V`) | Ground (`GND`) | Firmware / Script |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Joint 1: Base Yaw** | Rotates circular base left/right (`0°–180°`) | **ESP32 #1** | `arm_base_esp32` | **GPIO 13** (`D13`) | `5V` / `VIN` | `GND` | [`esp32_base_node.ino`](./slaves/esp32_base_node/esp32_base_node.ino) |
| **Joint 2: Shoulder Pitch** | Tilts black twin vertical link (`20°–160°`) | **ESP32 #2** | `arm_shoulder_esp32` | **GPIO 13** (`D13`) | `5V` / `VIN` | `GND` | [`esp32_shoulder_node.ino`](./slaves/esp32_shoulder_node/esp32_shoulder_node.ino) |
| **Joint 3: Elbow Pitch** | Raises/lowers grey forearm link (`20°–160°`) | **RP2040** *(Nano RP2040 / Pico W)* | `arm_elbow_rp2040` | **Pin 6** (`D6` / `GP6`) | `VUSB` / `VBUS` (`5V`) | `GND` | [`rp2040_elbow_node.ino`](./slaves/rp2040_elbow_node/rp2040_elbow_node.ino) |
| **Joint 4: Gripper Claw** | Opens/closes geared black jaws (`10°–95°`) | **Raspberry Pi** *(Ubuntu 24.04)* | `arm_gripper_rpi` | **BCM GPIO 18** *(Physical Pin 12)* | **Physical Pin 2 or 4** (`5V`) | **Physical Pin 6** (`GND`) | [`rpi_gripper_node.py`](./slaves/rpi_gripper_node/rpi_gripper_node.py) |

---

## 2. Raspberry Pi Setup (Newly Flashed Ubuntu 24.04 Server)

SSH into your Raspberry Pi running **Ubuntu 24.04 LTS Server** and run these commands to install the GPIO dependencies (`python3-lgpio`, `python3-rpi-lgpio`) and `openswarm-slave`:

```bash
# 1. Update apt and install Ubuntu 24.04 GPIO backends (works on both RPi 4 and RPi 5)
sudo apt update
sudo apt install -y python3 python3-pip python3-lgpio python3-rpi-lgpio python3-smbus2 python3-serial git

# 2. Install the OpenSwarm Linux Slave package
python3 -m pip install --break-system-packages --upgrade openswarm-slave

# 3. Clone the repo (or copy rpi_gripper_node.py) and start the Gripper Slave node:
git clone https://github.com/raihhann/OpenSwarm.git
cd OpenSwarm/projects/hydra_arm/slaves/rpi_gripper_node
sudo python3 rpi_gripper_node.py
```
*(Or simply run `bash setup_ubuntu24_rpi.sh` inside `slaves/rpi_gripper_node/`.)*

---

## 3. Flashing the 2× ESP32 and 1× RP2040 Boards

1. Open **Arduino IDE** and install **`SwarmNode`** from the Library Manager (or update to the latest version).
2. Flash **ESP32 #1** with [`slaves/esp32_base_node/esp32_base_node.ino`](./slaves/esp32_base_node/esp32_base_node.ino) (set your Wi-Fi SSID & password).
3. Flash **ESP32 #2** with [`slaves/esp32_shoulder_node/esp32_shoulder_node.ino`](./slaves/esp32_shoulder_node/esp32_shoulder_node.ino).
4. Flash **RP2040** with [`slaves/rp2040_elbow_node/rp2040_elbow_node.ino`](./slaves/rp2040_elbow_node/rp2040_elbow_node.ino).

---

## 4. Running HydraArm on Your Linux Master PC

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
* Dragging the slider moves the 3D arm AND sends real-time UDP servo commands to that joint's controller (`ESP32 #1`, `ESP32 #2`, `RP2040`, or `Raspberry Pi`)!

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
