/*
 * SwarmNode — Step 1: Complete ESP32 Slave Node Example
 *
 * Core Rule:
 *  - You ONLY declare Wi-Fi, Node ID, and attached hardware pins in setup().
 *  - void loop() is 100% EMPTY.
 *  - All robot control logic runs on the Linux Master over Wi-Fi!
 */

#include <SwarmNode.h>

SwarmNode node("tug_esp32");

void setup() {
    // 1. Connect to Wi-Fi
    node.connectWiFi("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD");

    // ========================================================================
    // 2. DECLARE ACTUATORS (Pins ONLY — Zero Control Logic!)
    // ========================================================================
    // Dual H-Bridge Motor Drivers:
    node.registerL298N("drive", 14, 27, 26, 32, 25, 33); // (name, ENA, IN1, IN2, ENB, IN3, IN4)
    // node.registerDRV8833("drive_drv", 14, 27, 26, 25); // 4-pin H-Bridge
    // node.registerMotor2Pin("winch", 12, 13);           // Single 2-pin DC motor

    // Servos, Steppers, Digital, PWM & DAC Outputs:
    // node.registerServo("gripper_servo", 13);           // 50Hz Hobby Servo (0..180 deg)
    // node.registerStepper("lifter_step", 16, 17);       // STEP=16, DIR=17 (A4988/DRV8825/TMC2209)
    // node.registerDigitalOutput("headlight", 2);        // GPIO Output (LED / Relay / Electromagnet)
    // node.registerPWMOutput("fan_pwm", 15);             // Variable PWM Output (0..255)
    // node.registerDACOutput("analog_out", 25);          // True Analog DAC Output (GPIO25/26)

    // ========================================================================
    // 3. DECLARE SENSORS (Pins/Addresses ONLY — Zero Control Logic!)
    // ========================================================================
    // Distance & Range:
    node.registerUltrasonic("front_sonar", 5, 18);       // HC-SR04 (TRIG=GPIO5, ECHO=GPIO18)
    // node.registerVL53L0X("laser_tof", 0x29, 21, 22);   // I2C Laser Rangefinder

    // Contact, IR, Line, Hall & Digital Inputs:
    node.registerBumper("front_bumper", 4);              // Contact switch on GPIO4 (INPUT_PULLUP)
    // node.registerIRSensor("ir_left", 19);              // IR obstacle / line sensor
    // node.registerDigitalInput("limit_sw", 23, true);   // Generic digital input

    // Wheel Odometry / Encoders (Hardware Interrupts):
    // node.registerQuadratureEncoder("left_enc", 34, 35);
    // node.registerTachometer("right_speed", 39);

    // Inertial & Power (I2C):
    // node.registerMPU6050("imu", 0x68, 21, 22);         // 6-DOF Accel + Gyro [ax,ay,az,gx,gy,gz]
    // node.registerINA219("power", 0x40, 21, 22);        // Bus Voltage (V) & Current (mA)

    // Universal I2C Sensor (Any I2C address & register: BME280, BMP280, BH1750, Compass, etc.):
    // node.registerGenericI2C("custom_i2c", 0x76, 0xFA, 2, 21, 22);

    // Analog, Battery, Touch, Environmental & System:
    // node.registerBatteryVoltage("vbat", 36);           // Analog ADC pin
    // node.registerAnalogInput("force_fsr", 39);         // Analog Force/Flex/LDR sensor
    // node.registerTouchPin("touch_pad", 12);            // ESP32 Capacitive Touch
    // node.registerDHT("env", 15, 22);                   // DHT22 Temp & Humidity [temp_C, hum_%]
    node.registerWiFiRSSI("rssi");                       // Wi-Fi Signal Strength (dBm)

    // ========================================================================
    // 4. START BACKGROUND DAEMON
    // ========================================================================
    node.start();
}

void loop() {
    // 100% EMPTY!
    // Background FreeRTOS task on Core 0 handles auto-discovery, 20Hz sensor
    // telemetry, actuator execution, and the 500ms hardware safety watchdog.
}
