#!/usr/bin/env python3
"""
OpenSwarm — Linux Slave Node Example
====================================
Runs on:
- Arduino UNO Q
- Arduino Portenta X8
- Raspberry Pi (3 / 4 / 5 / Zero 2W)
- Nvidia Jetson
- Any Linux Laptop / Ubuntu PC

Core Rule:
- You ONLY declare the Node ID and attached hardware pins/buses here.
- Zero control logic on the Slave! All control runs remotely on the Linux Master.
"""

from openswarm_slave import SwarmNode

# 1. Create Slave Node (auto-detects UNO Q, Portenta X8, RPi, Jetson, or Linux PC)
node = SwarmNode("linux_node")

# 2. Declare Actuators (Pins/Buses ONLY — Zero Control Logic!)
node.register_digital_output("led", 2)
# node.register_l298n("drive", 14, 27, 26, 32, 25, 33)
# node.register_i2c_actuator("pwm_driver", i2c_addr=0x40, bus_num=1)
# node.register_uart_actuator("mcu_bridge", port="/dev/ttyACM0", baud=115200)

# 3. Declare Sensors (Pins/Buses ONLY — Zero Control Logic!)
node.register_cpu_temp("cpu_temp")      # Streams SoC temperature (°C) at 20Hz
node.register_system_load("sys_load")   # Streams [load_1m, ram_used_%] at 20Hz
node.register_wifi_rssi("rssi")         # Streams Wi-Fi signal strength (dBm)
# node.register_ultrasonic("front_sonar", trig_pin=5, echo_pin=18)
# node.register_mpu6050("imu", i2c_addr=0x68, bus_num=1)

# 4. Start Background Slave Service
node.start()
