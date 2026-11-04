/*
 * SwarmNode — ESP32 Built-in LED Test (GPIO 2)
 *
 * Open Serial Monitor at 115200 baud after uploading!
 *  - Declares Wi-Fi, Node ID ("esp32_node"), and Pin 2 ("led") in setup().
 *  - void loop() is 100% EMPTY.
 */

#include <SwarmNode.h>

SwarmNode node("esp32_node");

void setup() {
    Serial.begin(115200);
    delay(1000); // Give Serial Monitor a moment to attach on boot

    Serial.println("==========================================");
    Serial.println("   OpenSwarm — Starting ESP32 Slave Node  ");
    Serial.println("==========================================");

    // 1. Connect to Wi-Fi (returns true if connected, false if timed out)
    bool connected = node.connectWiFi("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD");

    if (connected) {
        Serial.println("[SUCCESS] Wi-Fi Connected!");
        Serial.print("  -> Node ID : esp32_node\n");
        Serial.print("  -> IP Addr : ");
        Serial.println(WiFi.localIP());
        Serial.print("  -> Signal  : ");
        Serial.print(WiFi.RSSI());
        Serial.println(" dBm");
    } else {
        Serial.println("[FAILED] Could not connect to Wi-Fi! Check SSID/Password or 2.4GHz band.");
        return; // Stop setup if Wi-Fi failed
    }

    // 2. Register Pin 2 (ESP32 Built-in LED)
    node.registerDigitalOutput("led", 2);
    node.registerWiFiRSSI("rssi");

    // 3. Start background daemon
    node.start();
    Serial.println("[READY] Listening for Linux Master commands on UDP Port 4210...");
    Serial.println("==========================================");
}

void loop() {
    // 100% EMPTY! Controlled remotely from the Linux Master.
}
