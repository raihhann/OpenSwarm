/*
 * ============================================================================
 * OpenSwarm HydraArm — Joint 1: BASE YAW Servo Node (ESP32)
 * ============================================================================
 * Target Board : ESP32 (ESP32 Dev Module / NodeMCU-32S / ESP32-S3 / ESP32-C3)
 * Node ID      : "arm_base_esp32"
 * Joint Role   : Base Turntable Rotation (0..180 deg, Home = 90 deg)
 *
 * WIRING (Base SG90 / MG90S Servo -> ESP32):
 *   - Servo Orange/Yellow (Signal) -> ESP32 GPIO 13  (Pin D13)
 *   - Servo Red           (VCC 5V) -> ESP32 5V / VIN (or 5V Servo Rail)
 *   - Servo Brown/Black   (GND)    -> ESP32 GND      (MUST share common GND!)
 *
 * Core Rule:
 *   - setup() ONLY declares Wi-Fi, Node ID, and hardware pins.
 *   - void loop() is 100% EMPTY. All arm kinematics & UI control run on the
 *     Linux PC Master!
 * ============================================================================
 */

#include <SwarmNode.h>

SwarmNode node("arm_base_esp32");

void setup() {
    Serial.begin(115200);
    delay(500);

    Serial.println("==================================================");
    Serial.println("  OpenSwarm HydraArm — Joint 1: BASE (ESP32)      ");
    Serial.println("==================================================");

    // 1. Connect to Wi-Fi
    node.connectWiFi("lazycreep", "Porsch@91");

    // 2. Declare Attached Hardware Pins ONLY — Zero Control Logic!
    node.registerServo("servo", 13);        // Base Yaw SG90 Servo on GPIO 13
    node.registerDigitalOutput("led", 2);   // Onboard status LED on GPIO 2
    node.registerWiFiRSSI("rssi");          // Live 20 Hz Wi-Fi RSSI telemetry

    // 3. Start Background FreeRTOS Daemon on Core 0
    node.start();
}

void loop() {
    // 100% EMPTY! Controlled remotely by HydraArm Studio / CLI on Linux Master.
}
