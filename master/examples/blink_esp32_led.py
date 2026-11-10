#!/usr/bin/env python3
"""
OpenSwarm Master — Example 1: Control ESP32 Built-In LED (GPIO 2) & Read Live RSSI
===================================================================================
Run this script on your Linux laptop (or Windows PC) while your ESP32 is running
`ESP32_LED_Test.ino` on the same Wi-Fi network.

Usage:
    python blink_esp32_led.py
    # Or specify the ESP32 IP directly if your router blocks UDP broadcasts:
    python blink_esp32_led.py --ip 192.168.0.118
"""

import argparse
import time
from openswarm import SwarmMaster


def main():
    parser = argparse.ArgumentParser(description="Control ESP32 Slave LED from Linux Master")
    parser.add_argument("--node", default="esp32_node", help="Slave Node ID (default: esp32_node)")
    parser.add_argument("--ip", default=None, help="Optional direct IP (e.g. 192.168.0.118)")
    args = parser.parse_args()

    # 1. Start the Central Master
    master = SwarmMaster()

    # 2. Connect to the requested ESP32; never guess another robot's address.
    try:
        esp32 = master.connect(args.node, ip=args.ip, timeout=4.0)
    except TimeoutError as exc:
        master.close()
        parser.exit(1, f"{exc}\nUse --ip with the device's actual address if discovery is blocked.\n")

    print("==========================================================")
    print(f" Connected to Slave : {esp32.node_id} ({esp32.board})")
    print(f" Slave Address      : {esp32.ip}:{esp32.port}")
    print(" Press Ctrl+C to stop.")
    print("==========================================================")

    # 3. 100% of the control logic runs right here on the Master:
    led_state = False
    try:
        while True:
            led_state = not led_state

            # Command the registered "led" pin (GPIO 2) on the ESP32
            esp32.digital_write("led", led_state)

            # Read live 20Hz sensor telemetry streamed from the ESP32
            rssi = esp32.read("rssi")
            uptime_sec = esp32.uptime_ms / 1000.0

            print(
                f"[Master -> {esp32.node_id}] LED: {'ON ' if led_state else 'OFF'} | "
                f"Wi-Fi RSSI: {rssi:.0f} dBm | Slave Uptime: {uptime_sec:.1f}s"
            )
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[Master] Turning LED OFF and disconnecting...")
        esp32.digital_write("led", False)
        master.close()


if __name__ == "__main__":
    main()
