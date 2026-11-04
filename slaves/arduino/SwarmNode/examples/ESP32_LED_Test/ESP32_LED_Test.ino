/*
 * SwarmNode — ESP32 Built-in LED Test (GPIO 2)
 *
 * Tests remote pin control from your Linux Master before wiring motors/sensors.
 *  - Declares Wi-Fi, Node ID ("esp32_node"), and Pin 2 ("led") in setup().
 *  - void loop() is 100% EMPTY.
 */

#include <SwarmNode.h>

SwarmNode node("esp32_node");

void setup() {
    // 1. Connect to Wi-Fi
    node.connectWiFi("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD");

    // 2. Register Pin 2 (ESP32 Built-in LED)
    node.registerDigitalOutput("led", 2);   // Or: node.registerPin("led", 2, OUTPUT);
    node.registerWiFiRSSI("rssi");          // Streams Wi-Fi signal strength to Master

    // 3. Start background service
    node.start();
}

void loop() {
    // 100% EMPTY! Controlled remotely from the Linux Master.
}
