/*
 * ============================================================================
 * OpenSwarm HydraArm — Joint 2: SHOULDER PITCH MCU Bridge (Arduino UNO Q)
 * ============================================================================
 * Target Board : Arduino UNO Q (Zephyr architecture via Arduino IDE / App Lab)
 * Servo Pin    : Digital Pin 9 (D9)
 *
 * WHY NO <Servo.h>?
 *   Arduino's standard <Servo.h> does not support the `zephyr` architecture on
 *   the Arduino UNO Q yet. Instead, this sketch uses Zephyr RTOS's native
 *   multithreading (`k_thread` / `delayMicroseconds`) or hardware pulse timing
 *   to generate a rock-solid 50 Hz (20 ms period, 500..2400 us pulse) servo
 *   signal directly on Pin D9 while keeping `void loop()` 100% empty!
 *
 * WIRING (Shoulder SG90 / MG90S Servo -> Arduino UNO Q):
 *   - Servo Orange/Yellow (Signal) -> UNO Q Digital Pin 9 (D9)
 *   - Servo Red           (VCC 5V) -> 5V Power Supply / 5V Pin
 *   - Servo Brown/Black   (GND)    -> UNO Q GND (MUST share common GND!)
 * ============================================================================
 */

#include <Arduino.h>
#include <Arduino_RouterBridge.h>
#include <zephyr/kernel.h>

static const uint8_t SERVO_PIN = 9;
static volatile int g_targetPulseUs = 1978; // 140 deg default (500..2400 us)

// Dedicated Zephyr RTOS background thread for continuous 50 Hz servo holding on D9
K_THREAD_STACK_DEFINE(servo_stack_area, 1024);
static struct k_thread servo_thread_data;

static void servo_pwm_thread(void *, void *, void *) {
    while (true) {
        int pulse_us = g_targetPulseUs;
        digitalWrite(SERVO_PIN, HIGH);
        delayMicroseconds(pulse_us);
        digitalWrite(SERVO_PIN, LOW);
        // Complete the 20 ms (50 Hz) frame cleanly via Zephyr RTOS sleep
        k_msleep(18);
    }
}

void setServoAngle(int angle) {
    int clamped = constrain(angle, 0, 180);
    g_targetPulseUs = map(clamped, 0, 180, 500, 2400);
    // Toggle built-in LED on every servo update for visual confirmation
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
}

void setLedState(bool state) {
    digitalWrite(LED_BUILTIN, state ? HIGH : LOW);
}

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    pinMode(SERVO_PIN, OUTPUT);
    digitalWrite(SERVO_PIN, LOW);

    // 1. Initialize RouterBridge FIRST and register RPC functions BEFORE starting
    //    any high-frequency GPIO background thread
    Bridge.begin();
    Bridge.provide("set_servo", setServoAngle);
    Bridge.provide("set_led", setLedState);

    // 2. Start the 50 Hz Servo PWM background thread on Zephyr RTOS
    k_thread_create(
        &servo_thread_data,
        servo_stack_area,
        K_THREAD_STACK_SIZEOF(servo_stack_area),
        servo_pwm_thread,
        NULL, NULL, NULL,
        7, 0, K_NO_WAIT
    );
}

void loop() {
    // 100% EMPTY! Controlled remotely by the Linux Master via OpenSwarm.
}
