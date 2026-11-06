#!/usr/bin/env bash
# OpenSwarm Live Demonstration Launcher for Linux / Raspberry Pi
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}/master${PYTHONPATH:+:${PYTHONPATH}}"

echo "===================================================================="
echo "  OPENSWARM FLEET MASTER -- 3D DEMONSTRATION RECORDING SUITE"
echo "===================================================================="

# Start ESP32 Slave Emulator in background
python3 -m openswarm.virtual_slave --id tug_esp32 --board ESP32 --port 4210 &
PID_ESP32=$!

# Start RP2040 Slave Emulator in background
python3 -m openswarm.virtual_slave --id tug_rp2040 --board RP2040 --port 4212 &
PID_RP2040=$!

cleanup() {
    kill "$PID_ESP32" "$PID_RP2040" 2>/dev/null || true
    wait "$PID_ESP32" "$PID_RP2040" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Starting 3D Web Master on http://localhost:8080..."
python3 -m openswarm.web_server
