/*
 * SwarmNode — RP2040 Built-in LED & Onboard 6-Axis IMU Test
 * (Supports Arduino Nano RP2040 Connect & Raspberry Pi Pico W)
 *
 * Open Serial Monitor at 115200 baud after uploading!
 *  - Declares Wi-Fi, Node ID ("rp2040_node"), Built-in LED, and Onboard 6-DOF IMU in setup().
 *  - void loop() is 100% EMPTY.
 */

#include <SwarmNode.h>

SwarmNode node("rp2040_node");

void setup() {
    Serial.begin(115200);
    delay(1500); // Give native USB Serial a moment to attach

    Serial.println("==========================================");
    Serial.println("  OpenSwarm — Starting RP2040 Slave Node  ");
    Serial.println("==========================================");

    // 1. Connect to Wi-Fi
    bool connected = node.connectWiFi("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD");

    if (connected) {
        Serial.println("[SUCCESS] Wi-Fi Connected!");
        Serial.print("  -> Node ID : rp2040_node\n");
        Serial.print("  -> IP Addr : ");
        Serial.println(SwarmHAL::localIP());
        Serial.print("  -> Signal  : ");
        Serial.print(WiFi.RSSI());
        Serial.println(" dBm");
    } else {
        Serial.println("[FAILED] Could not connect to Wi-Fi! Check SSID/Password.");
        return;
    }

    // 2. Register Built-in LED (Pin 13 / LED_BUILTIN) & Sensors
    node.registerDigitalOutput("led", LED_BUILTIN);
    node.registerOnboardIMU("imu");   // Streams 6-Axis [ax, ay, az, gx, gy, gz] on Nano RP2040 Connect!
    node.registerWiFiRSSI("rssi");    // Streams Wi-Fi signal strength (dBm)

    // 3. Start background RTOS / Core 1 daemon
    node.start();
    Serial.println("[READY] Listening for Linux Master commands on UDP Port 4210...");
    Serial.println("==========================================");
}

void loop() {
    // 100% EMPTY! Controlled remotely from the Linux Master.
}
