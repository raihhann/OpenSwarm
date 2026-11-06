#!/usr/bin/env bash
# OpenSwarm Live Demonstration Launcher for Linux / Raspberry Pi
echo "===================================================================="
echo "  OPENSWARM FLEET MASTER -- 3D DEMONSTRATION RECORDING SUITE"
echo "===================================================================="

# Start ESP32 Slave Emulator in background
python3 -m openswarm.virtual_slave --id tug_esp32 --board ESP32 --port 4210 &
PID_ESP32=$!

# Start RP2040 Slave Emulator in background
python3 -m openswarm.virtual_slave --id tug_rp2040 --board RP2040 --port 4212 &
PID_RP2040=$!

echo "Starting 3D Web Master on http://localhost:8080..."
python3 -m openswarm.web_server

# Cleanup on exit
kill $PID_ESP32 $PID_RP2040
