#!/usr/bin/env bash
# ==============================================================================
# OpenSwarm HydraArm — Raspberry Pi (Ubuntu 24.04 Server) One-Shot Setup Script
# ==============================================================================
# Run this on your newly flashed Raspberry Pi (Ubuntu 24.04 LTS Server):
#   bash setup_ubuntu24_rpi.sh
# ==============================================================================
set -e

echo "=================================================================="
echo "  OpenSwarm HydraArm — Ubuntu 24.04 RPi Slave Dependency Installer"
echo "=================================================================="

# 1. Install system packages & GPIO libraries for Ubuntu 24.04 (Noble)
#    Note: On Ubuntu 24.04 (Kernel 6.8), python3-rpi-lgpio provides the drop-in
#    RPi.GPIO interface over modern /dev/gpiochip* for both RPi 4 and RPi 5!
sudo apt update
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-lgpio \
    python3-rpi-lgpio \
    python3-smbus2 \
    python3-serial \
    git

# 2. Allow your Ubuntu user to access /dev/gpiochip* without sudo
sudo usermod -aG dialout,sudo,video,plugdev "$USER" || true
if getent group gpio >/dev/null; then
    sudo usermod -aG gpio "$USER"
fi

# 3. Install openswarm-slave system-wide so both `python3` and `sudo python3` see it
sudo python3 -m pip install --break-system-packages --upgrade openswarm-slave

echo ""
echo "=================================================================="
echo " [SUCCESS] Raspberry Pi Ubuntu 24.04 is ready for OpenSwarm!"
echo " Wire your 2 Servos (Shoulder + Gripper) to the outer header row:"
echo "   1. SHOULDER SERVO (Joint 2):"
echo "      - Orange/Yellow (Signal) -> Physical Pin 8  (BCM GPIO 14)"
echo "      - Red           (5V)     -> Physical Pin 2  (5V)"
echo "      - Brown/Black   (GND)    -> Physical Pin 6  (GND)"
echo "   2. GRIPPER SERVO (Joint 4):"
echo "      - Orange/Yellow (Signal) -> Physical Pin 12 (BCM GPIO 18)"
echo "      - Red           (5V)     -> Physical Pin 4  (5V)"
echo "      - Brown/Black   (GND)    -> Physical Pin 14 (GND)"
echo ""
echo " Start the Raspberry Pi Slave Node with:"
echo "   sudo python3 rpi_gripper_node.py"
echo "=================================================================="
