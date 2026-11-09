/*
 * ============================================================================
 * OpenSwarm HydraArm — Joint 3: ELBOW PITCH Servo Node (RP2040)
 * ============================================================================
 * Target Board : Arduino Nano RP2040 Connect (or Raspberry Pi Pico W)
 * Node ID      : "arm_elbow_rp2040"
 * Joint Role   : Forearm Elbow Pitch (20..160 deg, Home = 90 deg)
 *
 * WIRING (Elbow SG90 / MG90S Servo -> RP2040):
 *   - Servo Orange/Yellow (Signal) -> Pin 6 (D6 on Nano RP2040 Connect / GP6 on Pico W)
 *   - Servo Red           (VCC 5V) -> VUSB / VBUS (5V pin) or 5V Servo Rail
 *   - Servo Brown/Black   (GND)    -> GND (MUST share common GND!)
 *
 * Core Rule:
 *   - setup() ONLY declares Wi-Fi, Node ID, and hardware pins.
 *   - void loop() is 100% EMPTY. All arm kinematics & UI control run on the
 *     Linux PC Master!
 * ============================================================================
 */

#include <SwarmNode.h>

SwarmNode node("arm_elbow_rp2040");

void setup() {
    Serial.begin(115200);
    delay(1500);

    Serial.println("=====================================================");
    Serial.println("  OpenSwarm HydraArm — Joint 3: ELBOW (RP2040 Node)  ");
    Serial.println("=====================================================");

    // 1. Connect to Wi-Fi
    node.connectWiFi("lazycreep", "Porsch@91");

    // 2. Declare Attached Hardware Pins ONLY — Zero Control Logic!
    node.registerServo("servo", 6);         // Elbow Pitch SG90 Servo on Pin 6 (D6 / GP6)
    node.registerDigitalOutput("led", 13);  // Built-in LED on Pin 13
    node.registerOnboardIMU("imu");         // Streams 6-Axis IMU [ax,ay,az,gx,gy,gz]
    node.registerWiFiRSSI("rssi");          // Streams 20 Hz Wi-Fi RSSI (dBm)

    // 3. Start Background Daemon
    node.start();
}

void loop() {
    // 100% EMPTY! Controlled remotely by HydraArm Studio / CLI on Linux Master.
}
