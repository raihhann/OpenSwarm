/*
 * SwarmNode — Arduino UNO Slave Node Example
 * (Supports Wi-Fi boards only: Arduino UNO R4 WiFi and UNO WiFi Rev2)
 *
 * Core Rule:
 *  - You ONLY declare Wi-Fi, Node ID, and attached hardware pins in setup().
 *  - void loop() is 100% EMPTY.
 *  - All robot control logic runs on the Linux Master!
 *
 * Tip: keep `#include <SwarmNode.h>` as the LAST include in your sketch.
 */

#include <SwarmNode.h>

SwarmNode node("tug_uno");

void setup() {
    // 1. Connect to Wi-Fi
    node.connectWiFi("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD");

    // 2. Declare Actuators (Pins ONLY — Zero Control Logic!)
    node.registerDigitalOutput("led", LED_BUILTIN);
    node.registerL298N("drive", 5, 4, 7, 6, 8, 9); // ENA=5(PWM), IN1=4, IN2=7, ENB=6(PWM), IN3=8, IN4=9

    // 3. Declare Sensors (Pins ONLY — Zero Control Logic!)
    node.registerUltrasonic("front_sonar", 10, 11); // TRIG=10, ECHO=11
    node.registerBumper("front_bumper", 12);        // Contact switch on D12 (INPUT_PULLUP)
    node.registerQuadratureEncoder("left_enc", 2, 3); // Hardware interrupt pin D2

    // 4. Start Slave Service
    node.start();
}

void loop() {
    // 100% EMPTY!
    // SwarmNode automatically hooks the background runtime so loop() stays empty.
}
