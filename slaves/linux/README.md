# OpenSwarm Linux Slave Agent (`openswarm-slave`)

Turns any Linux SBC (**Arduino UNO Q**, **Arduino Portenta X8**, **Raspberry Pi**, **Nvidia Jetson**) or **Linux Laptop** into a **Zero-Control-Logic OpenSwarm Slave Node**.

Speaks the **exact same UDP protocol (`4210` / `4211`)** as the `SwarmNode` C++ microcontroller library—so the Central Linux Master (`openswarm-master`) controls ESP32s, RP2040s, Portenta X8s, Arduino UNO Qs, and Raspberry Pis through one unified API!

---

## 1. Installation (On Arduino UNO Q, Portenta X8, Raspberry Pi, or Linux Laptop)

```bash
# Option A: Install directly from official PyPI:
pip install openswarm-slave

# Option B: Clone and install locally for development:
git clone https://github.com/raihhann/OpenSwarm.git
cd OpenSwarm/slaves/linux
pip install -e .
```

---

## 2. Instant Terminal Launch (`openswarm-slave` CLI)

You can turn any Linux machine into an active Slave node with a single command:

```bash
openswarm-slave --id portenta_x8 --led-pin 2
```

Then from your Master terminal (or another terminal on the same laptop!), test it immediately using `openswarm-master`:

```bash
openswarm scan
openswarm blink portenta_x8 --ip 127.0.0.1
```

---

## 3. Declarative Python Slave Script (`linux_slave_node.py`)

Just like `void setup()` on the microcontroller, you **only declare attached pins and sensors** (supports both `snake_case` and Arduino `camelCase` methods):

```python
from openswarm_slave import SwarmNode

node = SwarmNode("uno_q_node")

# Declare attached hardware ONLY — Zero Control Logic!
node.register_digital_output("led", 2)
node.register_l298n("drive", 14, 27, 26, 32, 25, 33)
node.register_ultrasonic("front_sonar", 5, 18)
node.register_cpu_temp("cpu_temp")
node.register_system_load("sys_load")
node.register_wifi_rssi("rssi")

# Start background daemon (500ms safety watchdog + 20Hz telemetry)
node.start()
```

---

## 4. Supported Linux Hardware Backends
* **GPIO & PWM:** Automatically uses `RPi.GPIO` (on Raspberry Pi), Linux kernel `/sys/class/gpio` (on **Portenta X8**, **Arduino UNO Q**, **Jetson**), or **Virtual GPIO Simulation Mode** when testing on a standard Linux/Windows laptop.
* **Buses (`I2C`, `SPI`, `UART`):** Supports `/dev/i2c-*` (`register_mpu6050`, `register_lsm6dsox`, `register_generic_i2c`, `register_i2c_actuator`) and `/dev/tty*` (`register_uart_sensor`, `register_uart_actuator`).
* **Linux System Telemetry:** `register_cpu_temp()` (`°C`), `register_system_load()` (`[load_1m, ram_%]`), and `register_wifi_rssi()` (`dBm`).
