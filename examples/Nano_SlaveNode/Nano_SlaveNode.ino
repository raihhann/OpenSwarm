/*
 * SwarmNode — Arduino Nano 33 IoT Slave Node Example
 * (For Nano RP2040 Connect see RP2040_SlaveNode; for Nano ESP32 see ESP32_SlaveNode.)
 *
 * Core Rule:
 *  - You ONLY declare Wi-Fi, Node ID, and attached hardware pins in setup().
 *  - void loop() is 100% EMPTY.
 *  - All robot control logic runs on the Linux Master!
 *
 * Tip: keep `#include <SwarmNode.h>` as the LAST include in your sketch.
 */

#include <SwarmNode.h>

SwarmNode node("tug_nano");

void setup() {
    // 1. Connect to Wi-Fi
    node.connectWiFi("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD");

    // 2. Declare Actuators (Pins ONLY — Zero Control Logic!)
    node.registerDigitalOutput("led", LED_BUILTIN);
    node.registerL298N("drive", 5, 4, 7, 6, 8, 9);

    // 3. Declare Sensors (Pins ONLY — Zero Control Logic!)
    node.registerUltrasonic("front_sonar", 10, 11);
    node.registerBumper("front_bumper", 12);
    node.registerOnboardIMU("imu");   // Built-in LSM6DS3 6-axis IMU (0x6A)

    // 4. Start Slave Service
    node.start();
}

void loop() {
    // 100% EMPTY!
}
