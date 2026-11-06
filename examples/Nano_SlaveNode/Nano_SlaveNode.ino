/*
 * SwarmNode — Arduino Nano Slave Node Example
 * (Supports Arduino Nano Classic ATmega328P, Nano Every, Nano 33 IoT, Nano RP2040, Nano ESP32)
 *
 * Core Rule:
 *  - You ONLY declare Network/Serial, Node ID, and attached hardware pins in setup().
 *  - void loop() is 100% EMPTY.
 *  - All robot control logic runs on the Linux Master!
 */

#include <SwarmNode.h>

SwarmNode node("tug_nano");

void setup() {
    // 1. Connect to Wi-Fi (on Nano 33 IoT / RP2040 / ESP32) or USB-Serial (on Classic Nano)
    node.connectWiFi("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD");

    // 2. Declare Actuators (Pins ONLY — Zero Control Logic!)
    node.registerDigitalOutput("led", LED_BUILTIN);
    node.registerL298N("drive", 5, 4, 7, 6, 8, 9);

    // 3. Declare Sensors (Pins ONLY — Zero Control Logic!)
    node.registerUltrasonic("front_sonar", 10, 11);
    node.registerBumper("front_bumper", 12);
    // node.registerOnboardIMU("imu"); // Uncomment on Nano 33 IoT or Nano RP2040 Connect!

    // 4. Start Slave Service
    node.start();
}

void loop() {
    // 100% EMPTY!
}
