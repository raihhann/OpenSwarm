#ifndef SWARM_NODE_H
#define SWARM_NODE_H

#include <Arduino.h>
#include "SwarmTypes.h"

#if defined(ESP32)
  #include "hal/hal_esp32.h"
#else
  #error "Step 1 (ESP32) HAL is currently loaded. UNO, Nano, and RP2040 HALs are next!"
#endif

class SwarmNode {
public:
    explicit SwarmNode(const char* node_id, uint16_t udp_port = SWARM_DEFAULT_PORT);

    // ------------------------------------------------------------------------
    // 1. Network Setup
    // ------------------------------------------------------------------------
    bool connectWiFi(const char* ssid, const char* password, uint32_t timeout_ms = 15000);

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
    bool registerUltrasonic(const char* name, uint8_t trigPin, uint8_t echoPin);
    bool registerVL53L0X(const char* name, uint8_t i2cAddr = 0x29, uint8_t sdaPin = 255, uint8_t sclPin = 255);
    bool registerQuadratureEncoder(const char* name, uint8_t pinA, uint8_t pinB);
    bool registerTachometer(const char* name, uint8_t pin);
    bool registerMPU6050(const char* name, uint8_t i2cAddr = 0x68, uint8_t sdaPin = 255, uint8_t sclPin = 255);
    bool registerINA219(const char* name, uint8_t i2cAddr = 0x40, uint8_t sdaPin = 255, uint8_t sclPin = 255);
    bool registerBumper(const char* name, uint8_t pin, bool pullup = true);
    bool registerDigitalInput(const char* name, uint8_t pin, bool pullup = false);
    bool registerIRSensor(const char* name, uint8_t pin, bool pullup = false);
    bool registerAnalogInput(const char* name, uint8_t pin);
    bool registerBatteryVoltage(const char* name, uint8_t adcPin);
    bool registerTouchPin(const char* name, uint8_t touchPin);
    bool registerDHT(const char* name, uint8_t pin, uint8_t model = 22);
    bool registerWiFiRSSI(const char* name = "rssi");

    // ------------------------------------------------------------------------
    // 4. Universal Protocol & Custom Hardware API (UART, I2C, SPI, LoRa, Custom)
    // ------------------------------------------------------------------------
    // I2C Protocol (Read & Write any I2C Sensor/Actuator):
    bool registerGenericI2C(const char* name, uint8_t i2cAddr, uint8_t regAddr, uint8_t numBytes = 2,
                            uint8_t sdaPin = 255, uint8_t sclPin = 255);
    bool registerI2CActuator(const char* name, uint8_t i2cAddr, uint8_t sdaPin = 255, uint8_t sclPin = 255);

    // SPI Protocol (Read & Write any SPI Sensor/Actuator):
    bool registerSPISensor(const char* name, uint8_t csPin, uint8_t readReg, uint8_t numBytes = 2,
                           uint8_t sckPin = 255, uint8_t misoPin = 255, uint8_t mosiPin = 255,
                           uint32_t clockHz = 1000000UL);
    bool registerSPIActuator(const char* name, uint8_t csPin,
                             uint8_t sckPin = 255, uint8_t misoPin = 255, uint8_t mosiPin = 255,
                             uint32_t clockHz = 1000000UL);

    // UART Protocol (GPS, UART LiDAR, RS485, Serial Transceivers):
    bool registerUARTSensor(const char* name, uint8_t rxPin, uint8_t txPin,
                            uint32_t baud = 9600, uint8_t uartNum = 2);
    bool registerUARTActuator(const char* name, uint8_t rxPin, uint8_t txPin,
                              uint32_t baud = 9600, uint8_t uartNum = 2);

    // LoRa Transceivers (Both UART LoRa like E32/RYLR998 AND SPI LoRa like SX1276/SX1278/RFM95):
    bool registerLoRaUART(const char* name, uint8_t rxPin, uint8_t txPin,
                          uint32_t baud = 9600, uint8_t m0Pin = 255, uint8_t m1Pin = 255, uint8_t uartNum = 2);
    bool registerLoRaSPI(const char* name, uint8_t csPin, uint8_t rstPin = 255, uint8_t irqPin = 255,
                         uint32_t freqHz = 868000000UL,
                         uint8_t sckPin = 255, uint8_t misoPin = 255, uint8_t mosiPin = 255);

    // User-Defined Custom Callbacks (For ANY 3rd-party library or custom protocol — loop() stays empty!):
    bool registerCustomSensor(const char* name, SwarmCustomSensorFn readCallback);
    bool registerCustomSensorMulti(const char* name, SwarmCustomMultiSensorFn readMultiCallback);
    bool registerCustomActuator(const char* name, SwarmCustomActuatorFn writeCallback);

    // ------------------------------------------------------------------------
    // 5. Start Background Daemon (Leaves void loop() 100% empty!)
    // ------------------------------------------------------------------------
    void start();

    // Internal tick called by background FreeRTOS task
    void _backgroundTick();

private:
    char _nodeId[24];
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
    bool _watchdogTripped = false;

    void _handleIncomingPacket();
    void _processCommand(const char* json, IPAddress senderIP, uint16_t senderPort);
    void _sendHelloBroadcast();
    void _sendTelemetry();
    void _emergencyStopAll();

    static bool _extractString(const char* json, const char* key, char* outBuf, size_t maxLen);
    static bool _extractInt(const char* json, const char* key, int16_t& outVal);
};

#endif // SWARM_NODE_H
