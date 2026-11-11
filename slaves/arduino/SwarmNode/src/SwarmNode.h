#ifndef SWARM_NODE_H
#define SWARM_NODE_H

#include <Arduino.h>
#include "SwarmTypes.h"

// Supported boards (Wi-Fi capable only):
//   ESP32 family                : FreeRTOS task on Core 0
//   Arduino Nano RP2040 Connect : Mbed RTOS thread
//   Raspberry Pi Pico W         : auto-loop hook on Core 0 (same core as the CYW43 Wi-Fi driver)
//   Arduino UNO R4 WiFi / UNO WiFi Rev2 / Nano 33 IoT : auto-loop hook
#if defined(ESP32)
  #include "hal/hal_esp32.h"
  #define SWARM_HAS_RTOS_DAEMON 1
#elif defined(ARDUINO_NANO_RP2040_CONNECT) || defined(ARDUINO_ARCH_MBED_RP2040)
  #include "hal/hal_rp2040.h"
  #define SWARM_HAS_RTOS_DAEMON 1
#elif defined(ARDUINO_ARCH_RP2040) || defined(TARGET_RP2040)
  #include "hal/hal_rp2040.h"
  #define SWARM_HAS_RTOS_DAEMON 0
#elif defined(ARDUINO_UNOR4_WIFI) || defined(ARDUINO_AVR_UNO_WIFI_REV2)
  #include "hal/hal_uno.h"
  #define SWARM_HAS_RTOS_DAEMON 0
#elif defined(ARDUINO_SAMD_NANO_33_IOT)
  #include "hal/hal_nano.h"
  #define SWARM_HAS_RTOS_DAEMON 0
#else
  #error "Unsupported board. SwarmNode supports Wi-Fi boards only: ESP32, Nano RP2040 Connect, Pico W, UNO R4 WiFi, UNO WiFi Rev2, Nano 33 IoT."
#endif

// On boards without a background RTOS daemon, automatically hook the Arduino
// main loop so the user's `void loop() {}` in their sketch stays 100% empty!
//
// NOTE: This works by renaming the token `loop` to `_swarmUserLoop` for all code
// that comes AFTER this header. Always `#include <SwarmNode.h>` as the LAST
// include in your sketch so other libraries' `loop()` methods (e.g. `mqtt.loop()`)
// declared in their headers are not renamed.
#if !SWARM_HAS_RTOS_DAEMON && !defined(SWARM_NODE_CPP_INTERNAL)
  void _swarmUserLoop();
  #define loop _swarmUserLoop
#endif

class SwarmNode {
public:
    explicit SwarmNode(const char* node_id, uint16_t udp_port = SWARM_DEFAULT_PORT);

    // ------------------------------------------------------------------------
    // 1. Network / Transport Setup
    // ------------------------------------------------------------------------
    bool connectWiFi(const char* ssid, const char* password, uint32_t timeout_ms = 20000);

    // ------------------------------------------------------------------------
    // 2. Standard Actuator Registration API (Motors, Servos, Steppers, GPIO)
    // ------------------------------------------------------------------------
    bool registerL298N(const char* name,
                       uint8_t ena, uint8_t in1, uint8_t in2,
                       uint8_t enb, uint8_t in3, uint8_t in4);

    bool registerDRV8833(const char* name,
                         uint8_t in1, uint8_t in2,
                         uint8_t in3, uint8_t in4);

    bool registerMotor2Pin(const char* name, uint8_t pinA, uint8_t pinB);
    bool registerServo(const char* name, uint8_t pin);
    bool registerStepper(const char* name, uint8_t stepPin, uint8_t dirPin, uint8_t enPin = 255);
    bool registerDigitalOutput(const char* name, uint8_t pin);
    bool registerPWMOutput(const char* name, uint8_t pin);
    bool registerDACOutput(const char* name, uint8_t pin);
    bool registerPin(const char* name, uint8_t pin, uint8_t mode = OUTPUT);

    // ------------------------------------------------------------------------
    // 3. Standard Sensor Registration API
    // ------------------------------------------------------------------------
    // Distance / Range:
    bool registerUltrasonic(const char* name, uint8_t trigPin, uint8_t echoPin);
    bool registerVL53L0X(const char* name, uint8_t i2cAddr = 0x29, uint8_t sdaPin = 255, uint8_t sclPin = 255);

    // Wheel Odometry / Encoders (Hardware Interrupts):
    bool registerQuadratureEncoder(const char* name, uint8_t pinA, uint8_t pinB);
    bool registerTachometer(const char* name, uint8_t pin);

    // Inertial (6-DOF IMU) & Power Monitors (I2C):
    bool registerMPU6050(const char* name, uint8_t i2cAddr = 0x68, uint8_t sdaPin = 255, uint8_t sclPin = 255);
    bool registerLSM6DSOX(const char* name, uint8_t i2cAddr = 0x6A, uint8_t sdaPin = 255, uint8_t sclPin = 255);
    bool registerOnboardIMU(const char* name = "imu"); // Built-in 6-Axis IMU on Nano RP2040 / Nano 33 IoT (0x6A)
    bool registerINA219(const char* name, uint8_t i2cAddr = 0x40, uint8_t sdaPin = 255, uint8_t sclPin = 255);

    // Digital / Contact / IR / Line / Hall / PIR:
    bool registerBumper(const char* name, uint8_t pin, bool pullup = true);
    bool registerDigitalInput(const char* name, uint8_t pin, bool pullup = false);
    bool registerIRSensor(const char* name, uint8_t pin, bool pullup = false);

    // Analog / Environmental / Touch / System:
    bool registerAnalogInput(const char* name, uint8_t pin);
    bool registerBatteryVoltage(const char* name, uint8_t adcPin);
    bool registerTouchPin(const char* name, uint8_t touchPin);
    bool registerDHT(const char* name, uint8_t pin, uint8_t model = 22);
    bool registerWiFiRSSI(const char* name = "rssi");

    // ------------------------------------------------------------------------
    // 4. Universal Bus Protocols & Custom Hardware API (I2C, SPI, UART, Custom)
    // ------------------------------------------------------------------------
    bool registerGenericI2C(const char* name, uint8_t i2cAddr, uint8_t regAddr, uint8_t numBytes = 2,
                            uint8_t sdaPin = 255, uint8_t sclPin = 255);
    bool registerI2CActuator(const char* name, uint8_t i2cAddr, uint8_t sdaPin = 255, uint8_t sclPin = 255);

    bool registerSPISensor(const char* name, uint8_t csPin, uint8_t readReg, uint8_t numBytes = 2,
                           uint8_t sckPin = 255, uint8_t misoPin = 255, uint8_t mosiPin = 255,
                           uint32_t clockHz = 1000000UL);
    bool registerSPIActuator(const char* name, uint8_t csPin,
                             uint8_t sckPin = 255, uint8_t misoPin = 255, uint8_t mosiPin = 255,
                             uint32_t clockHz = 1000000UL);

    bool registerUARTSensor(const char* name, uint8_t rxPin = 255, uint8_t txPin = 255,
                            uint32_t baud = 9600, uint8_t uartNum = 1);
    bool registerUARTActuator(const char* name, uint8_t rxPin = 255, uint8_t txPin = 255,
                              uint32_t baud = 9600, uint8_t uartNum = 1);

    bool registerCustomSensor(const char* name, SwarmCustomSensorFn readCallback);
    bool registerCustomSensorMulti(const char* name, SwarmCustomMultiSensorFn readMultiCallback);
    bool registerCustomActuator(const char* name, SwarmCustomActuatorFn writeCallback);

    // ------------------------------------------------------------------------
    // 5. Start Background Daemon (Leaves void loop() 100% empty!)
    // ------------------------------------------------------------------------
    void start();

    // Internal tick called by background daemon / auto-loop hook
    void _backgroundTick();

private:
    char _nodeId[20];
    uint16_t _udpPort;
    WiFiUDP _udp;

    ActuatorDescriptor _actuators[SWARM_MAX_ACTUATORS];
    uint8_t _actuatorCount = 0;

    SensorDescriptor _sensors[SWARM_MAX_SENSORS];
    uint8_t _sensorCount = 0;
    uint8_t _encoderCount = 0;

    IPAddress _masterIP;
    uint16_t _masterPort = 0;
    bool _masterConnected = false;

    uint32_t _lastMasterPacketMs = 0;
    uint32_t _lastTelemetryMs = 0;
    uint32_t _lastHelloMs = 0;
    uint32_t _lastServoMs = 0;
    bool _watchdogTripped = false;
    int16_t _lastCmdSeq = 0;
    uint16_t _watchdogTrips = 0;
    uint16_t _droppedOutOfOrder = 0;
    uint16_t _leaseExpirations = 0;

    void _handleIncomingPacket();
    void _processCommand(const char* json, IPAddress senderIP, uint16_t senderPort);
    void _sendHelloBroadcast();
    void _sendTelemetry();
    void _stopActuator(ActuatorDescriptor& act);
    void _emergencyStopAll();

    static int _appendf(char* buf, size_t cap, int offset, const char* fmt, ...);
    static int _appendFixed2(char* buf, size_t cap, int offset, const char* prefix, float v);

    static bool _extractString(const char* json, const char* key, char* outBuf, size_t maxLen);
    static bool _extractInt(const char* json, const char* key, int16_t& outVal);
};

#endif // SWARM_NODE_H
