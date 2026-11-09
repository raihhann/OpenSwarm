/*
 * ============================================================================
 * OpenSwarm HydraArm — Joint 2: SHOULDER PITCH MCU Bridge (Arduino UNO Q)
 * ============================================================================
 * Target Board : Arduino UNO Q (STM32U585 MCU side via Arduino IDE / App Lab)
 * Servo Pin    : Digital Pin 9 (D9 — Hardware PWM)
 *
 * HOW ARDUINO UNO Q WORKS:
 *   The Arduino UNO Q has a dual-processor architecture:
 *     1. STM32U585 MCU (runs this sketch, drives the real-time 50Hz Servo PWM on Pin D9)
 *     2. Qualcomm DragonWing Linux MPU (runs `unoq_shoulder_node.py`, connects to
 *        the OpenSwarm Linux Master over Wi-Fi UDP and calls `set_servo` via RPC Bridge)
 *
 * WIRING (Shoulder SG90 / MG90S Servo -> Arduino UNO Q):
 *   - Servo Orange/Yellow (Signal) -> UNO Q Digital Pin 9 (D9)
 *   - Servo Red           (VCC 5V) -> 5V Power Supply / 5V Pin
 *   - Servo Brown/Black   (GND)    -> UNO Q GND (MUST share common GND!)
 * ============================================================================
 */

#include <Arduino_RouterBridge.h>
#include <Servo.h>

Servo shoulderServo;

void setServoAngle(int angle) {
    int clamped = constrain(angle, 0, 180);
    shoulderServo.write(clamped);
}

void setLedState(bool state) {
    digitalWrite(LED_BUILTIN, state ? HIGH : LOW);
}

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    Bridge.begin();

    shoulderServo.attach(9);   // Shoulder Servo signal wire on Pin D9
    shoulderServo.write(90);   // Start at 90 deg neutral position

    // Expose RPC handlers to the UNO Q Linux processor (`unoq_shoulder_node.py`)
    Bridge.provide_safe("set_servo", setServoAngle);
    Bridge.provide_safe("set_led", setLedState);
}

void loop() {
    // 100% EMPTY! Controlled remotely by the Linux Master via OpenSwarm.
}
