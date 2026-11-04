# OpenSwarm Master (`openswarm-master`)

The Central Linux Master SDK & CLI for the [**OpenSwarm**](https://github.com/raihhann/OpenSwarm) Distributed Hardware-Agnostic Robotics Framework.

* **Zero Slave Control Logic:** All sensor processing, state machines, kinematics, and actuator commands run here on the Master.
* **Zero External Dependencies:** Pure Python 3 standard library (`socket`, `threading`, `json`) for instant installation on any Linux laptop, Ubuntu PC, Raspberry Pi, or Windows machine.
* **Auto-Discovery + Direct IP:** Automatically discovers Slaves via UDP port `4211` (`HELLO` broadcast) or connects directly by IP (`192.168.x.x:4210`).
* **Built-In Keepalive:** Sends a 200 ms background heartbeat (`PING`) to keep the Slave's 500 ms hardware safety watchdog active and stream 20 Hz sensor telemetry (`STATE`).

---

## 1. Installation

### Option A: Install from PyPI (Recommended)
```bash
pip install openswarm-master
```

### Option B: Clone & Install in Editable Mode (Recommended for Development)
```bash
git clone https://github.com/raihhann/OpenSwarm.git
cd OpenSwarm/master
pip install -e .
```

---

## 2. Terminal CLI (`openswarm`)

```bash
# Scan the local Wi-Fi network for active Slave nodes:
openswarm scan

# Blink the built-in LED ("led" on GPIO 2) on esp32_node and print live 20 Hz RSSI:
openswarm blink esp32_node --ip 192.168.0.118
```

---

## 3. Python API Reference

```python
import time
from openswarm import SwarmMaster

master = SwarmMaster()

# Connect by Node ID (auto-discovers on LAN, or pass ip="192.168.0.118" directly)
bot = master.connect("esp32_node", ip="192.168.0.118")

# 1. Digital & PWM Pin Control
bot.digital_write("led", 1)                  # Named digital output HIGH
bot.digital_write("led", 0)                  # Named digital output LOW
bot.pwm_write("led", 128)                    # Named PWM output (0..255)
bot.pin_write(2, 1)                          # Direct GPIO pin number write

# 2. Motor, Servo & Stepper Control
bot.drive("drive", left=180, right=180)      # Dual H-Bridge (L298N / DRV8833)
bot.servo("gripper", angle=90)               # Hobby Servo (0..180 deg)
bot.stepper("lifter", steps=200)             # Stepper driver
bot.stop()                                   # Immediate emergency stop

# 3. Universal Bus & Custom Actuator Control (LoRa, SPI, I2C, UART)
bot.send_bus("lora_radio", data="PING_SWARM")
bot.write_reg("i2c_pwm_chip", reg=0x06, val=200)

# 4. Live 20 Hz Sensor Telemetry
print("RSSI:", bot.read("rssi"))
print("All Sensors:", bot.sensors)

master.close()
```
