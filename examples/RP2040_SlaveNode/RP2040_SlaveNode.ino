/*
 * SwarmNode — Complete RP2040 Slave Node Example
 * (Supports Arduino Nano RP2040 Connect & Raspberry Pi Pico W)
 *
 * Core Rule:
 *  - You ONLY declare Wi-Fi, Node ID, and attached hardware pins in setup().
 *  - void loop() is 100% EMPTY.
 *  - All robot control logic runs on the Linux Master over Wi-Fi!
 */

#include <SwarmNode.h>

SwarmNode node("tug_rp2040");

void setup() {
    // 1. Connect to Wi-Fi
    node.connectWiFi("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD");

    // ========================================================================
    // 2. DECLARE ACTUATORS (Pins ONLY — Zero Control Logic!)
    // ========================================================================
    // Dual H-Bridge Motor Drivers (e.g. L298N on D2..D7):
    node.registerL298N("drive", 2, 3, 4, 5, 6, 7); // (name, ENA, IN1, IN2, ENB, IN3, IN4)
    // node.registerDRV8833("drive_drv", 2, 3, 4, 5);
    // node.registerServo("gripper_servo", 8);
    // node.registerStepper("lifter_step", 9, 10);
    node.registerDigitalOutput("led", LED_BUILTIN);

    // ========================================================================
    // 3. DECLARE SENSORS (Pins/Addresses ONLY — Zero Control Logic!)
    // ========================================================================
    // Onboard 6-Axis IMU (ST LSM6DSOX at 0x6A on Arduino Nano RP2040 Connect):
    node.registerOnboardIMU("imu");                  // Streams [ax, ay, az, gx, gy, gz] at 20Hz!

    // Distance & Contact:
    node.registerUltrasonic("front_sonar", 8, 9);    // HC-SR04 (TRIG=D8, ECHO=D9)
    node.registerBumper("front_bumper", 10);         // Limit switch on D10 (INPUT_PULLUP)

    // Wheel Odometry / Encoders (Hardware Interrupts):
    // node.registerQuadratureEncoder("left_enc", 11, 12);

    // Generic I2C / SPI / UART Bus Sensors & Actuators:
    // node.registerGenericI2C("tof_raw", 0x29, 0x1E, 2);
    // node.registerUARTSensor("serial_sensor", 0, 1, 9600);

    // System Telemetry:
    node.registerWiFiRSSI("rssi");

    // ========================================================================
    // 4. START BACKGROUND DAEMON
    // ========================================================================
    node.start();
}

void loop() {
    // 100% EMPTY!
    // Background Mbed RTOS Thread (or RP2040 Core 1) handles discovery, 20Hz
    // sensor telemetry, actuator execution, and the 500ms safety watchdog.
}
