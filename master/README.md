# OpenSwarm Master (`openswarm-master`)

The Central Linux Master SDK & CLI for the [**OpenSwarm**](https://github.com/raihhann/OpenSwarm) Distributed Hardware-Agnostic Robotics Framework.

* **Zero Slave Control Logic:** All sensor processing, state machines, kinematics, and actuator commands run here on the Master.
* **Zero Core Dependencies:** The SDK and CLI use only the Python standard library (`socket`, `threading`, `json`) and run on Linux, Windows, and macOS.
* **Auto-Discovery + Direct IP:** Automatically discovers Slaves via UDP port `4211` (`HELLO` broadcast) or connects directly by IP (`192.168.x.x:4210`).
* **Built-In Keepalive:** Sends a 200 ms background heartbeat (`PING`) to keep the Slave's 500 ms software transport watchdog active and stream 20 Hz sensor telemetry (`STATE`).

Discovery is passive: scanning does not start keepalives or stop discovered nodes.
Use `connect()` to wait for verified telemetry, or `subscribe(node_id)` to request it
without blocking. The first actuator command also activates a discovered node.
Shutdown stops active nodes only. `SwarmMaster` supports `with` for deterministic cleanup.
Use `read(name, default=None, max_age=0.25)` when stale readings should be rejected.
These are local session semantics; exclusive controller ownership is not implemented.

---

## 1. Installation

### Option A: Install from PyPI (Recommended)
```bash
pip install openswarm-master
```

For the optional browser-based 3D demo:
```bash
pip install "openswarm-master[demo]"
```

Launch each virtual node in its own terminal:
```bash
python -m openswarm.virtual_slave --id tug_esp32 --board ESP32 --port 4210
```
```bash
python -m openswarm.virtual_slave --id tug_rp2040 --board RP2040 --port 4212
```
In a third terminal, run the web server:
```bash
python -m openswarm.web_server
```
It binds to `127.0.0.1` and is available at `http://localhost:8080`.

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

# 3. Universal Bus & Custom Actuator Control (UART, SPI, I2C, Custom)
bot.send_bus("uart_link", data="PING_SWARM")
bot.write_reg("i2c_pwm_chip", reg=0x06, val=200)

# 4. Live 20 Hz Sensor Telemetry
print("RSSI:", bot.read("rssi"))
print("All Sensors:", bot.sensors)
print("Telemetry age (s):", bot.telemetry_age)   # How fresh the latest reading is

master.close()
```

---

## 4. 3D Simulation Demo (no hardware)

A browser-based 3D fleet demo and the virtual slave emulator are included in the
`openswarm-master` package. Install the optional `demo` extra to add `aiohttp`.
The UDP control protocol is unauthenticated and unencrypted; use it only on a
trusted, isolated network and keep the demo server on localhost.
