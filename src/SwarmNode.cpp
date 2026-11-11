#define SWARM_NODE_CPP_INTERNAL 1
#include "SwarmNode.h"
#include "SwarmProtocol.h"
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>

static SwarmNode* _activeSwarmNode = nullptr;

// On boards without a background RTOS daemon (Pico W, UNO R4 WiFi, UNO WiFi Rev2,
// Nano 33 IoT), provide the real `loop()` entry point that runs the background
// network/telemetry tick and then calls the user's (empty) `_swarmUserLoop()`.
#if !SWARM_HAS_RTOS_DAEMON
extern void _swarmUserLoop();
void loop() {
    if (_activeSwarmNode) {
        _activeSwarmNode->_backgroundTick();
    }
    _swarmUserLoop();
}
#endif

SwarmNode::SwarmNode(const char* node_id, uint16_t udp_port)
    : _udpPort(udp_port) {
    strncpy(_nodeId, node_id, sizeof(_nodeId) - 1);
    _nodeId[sizeof(_nodeId) - 1] = '\0';
    if (!SwarmProtocol::validName(node_id, sizeof(_nodeId) - 1)) _nodeId[0] = '\0';
}

bool SwarmNode::connectWiFi(const char* ssid, const char* password, uint32_t timeout_ms) {
    Serial.begin(115200);
    delay(100);
    Serial.println();
    Serial.print("[SwarmNode] Connecting node '");
    Serial.print(_nodeId);
    Serial.print("' (");
    Serial.print(SwarmHAL::boardName());
    Serial.print(") to network: ");
    Serial.println(ssid);

    bool ok = SwarmHAL::connectNetwork(ssid, password, timeout_ms);
    if (ok) {
        Serial.print("[SwarmNode] Ready! Transport: ");
        Serial.print(SwarmHAL::localIP());
        Serial.print(" | Port: ");
        Serial.println(_udpPort);
    } else {
        Serial.println("[SwarmNode] ERROR: Network connection timed out!");
    }
    return ok;
}

// ============================================================================
// STANDARD ACTUATOR REGISTRATION
// ============================================================================

bool SwarmNode::registerL298N(const char* name,
                              uint8_t ena, uint8_t in1, uint8_t in2,
                              uint8_t enb, uint8_t in3, uint8_t in4) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_L298N;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.pins[0] = ena; act.pins[1] = in1; act.pins[2] = in2;
    act.pins[3] = enb; act.pins[4] = in3; act.pins[5] = in4;
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerDRV8833(const char* name,
                                uint8_t in1, uint8_t in2,
                                uint8_t in3, uint8_t in4) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_DRV8833;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.pins[0] = in1; act.pins[1] = in2;
    act.pins[2] = in3; act.pins[3] = in4;
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerMotor2Pin(const char* name, uint8_t pinA, uint8_t pinB) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_MOTOR_2PIN;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.pins[0] = pinA;
    act.pins[1] = pinB;
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerServo(const char* name, uint8_t pin) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_SERVO;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.pins[0] = pin;
    act.val1 = 90;
    act.bus_addr = 0;  // Set to 1 once the Master commands an angle (enables 50 Hz holding)
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerStepper(const char* name, uint8_t stepPin, uint8_t dirPin, uint8_t enPin) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_STEPPER;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.pins[0] = stepPin;
    act.pins[1] = dirPin;
    act.pins[2] = enPin;
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerDigitalOutput(const char* name, uint8_t pin) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_DIGITAL_OUT;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.pins[0] = pin;
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerPWMOutput(const char* name, uint8_t pin) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_PWM_OUT;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.pins[0] = pin;
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerDACOutput(const char* name, uint8_t pin) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_DAC_OUT;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.pins[0] = pin;
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerPin(const char* name, uint8_t pin, uint8_t mode) {
    if (mode == INPUT) {
        return registerDigitalInput(name, pin, false);
    } else if (mode == INPUT_PULLUP) {
        return registerDigitalInput(name, pin, true);
    } else {
        return registerDigitalOutput(name, pin);
    }
}

// ============================================================================
// STANDARD SENSOR REGISTRATION
// ============================================================================

bool SwarmNode::registerUltrasonic(const char* name, uint8_t trigPin, uint8_t echoPin) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_ULTRASONIC;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.pins[0] = trigPin;
    sens.pins[1] = echoPin;
    SwarmHAL::setupSensor(sens);
    return true;
}

bool SwarmNode::registerVL53L0X(const char* name, uint8_t i2cAddr, uint8_t sdaPin, uint8_t sclPin) {
    return registerGenericI2C(name, i2cAddr, 0x1E, 2, sdaPin, sclPin);
}

bool SwarmNode::registerQuadratureEncoder(const char* name, uint8_t pinA, uint8_t pinB) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS || _encoderCount >= SWARM_MAX_ENCODERS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_ENCODER_QUAD;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.pins[0] = pinA;
    sens.pins[1] = pinB;
    sens.sub_index = _encoderCount++;
    SwarmHAL::setupSensor(sens);
    return true;
}

bool SwarmNode::registerTachometer(const char* name, uint8_t pin) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS || _encoderCount >= SWARM_MAX_ENCODERS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_TACHOMETER;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.pins[0] = pin;
    sens.pins[1] = 255;
    sens.sub_index = _encoderCount++;
    SwarmHAL::setupSensor(sens);
    return true;
}

bool SwarmNode::registerMPU6050(const char* name, uint8_t i2cAddr, uint8_t sdaPin, uint8_t sclPin) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_MPU6050;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.i2c_addr = i2cAddr;
    sens.pins[0] = sdaPin;
    sens.pins[1] = sclPin;
    sens.value_count = 6;
    SwarmHAL::setupSensor(sens);
    return true;
}

bool SwarmNode::registerLSM6DSOX(const char* name, uint8_t i2cAddr, uint8_t sdaPin, uint8_t sclPin) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_LSM6DSOX;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.i2c_addr = i2cAddr;
    sens.pins[0] = sdaPin;
    sens.pins[1] = sclPin;
    sens.value_count = 6;
    SwarmHAL::setupSensor(sens);
    return true;
}

bool SwarmNode::registerOnboardIMU(const char* name) {
    return registerLSM6DSOX(name, 0x6A, 255, 255);
}

bool SwarmNode::registerINA219(const char* name, uint8_t i2cAddr, uint8_t sdaPin, uint8_t sclPin) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_INA219;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.i2c_addr = i2cAddr;
    sens.pins[0] = sdaPin;
    sens.pins[1] = sclPin;
    sens.value_count = 2;
    SwarmHAL::setupSensor(sens);
    return true;
}

bool SwarmNode::registerBumper(const char* name, uint8_t pin, bool pullup) {
    return registerDigitalInput(name, pin, pullup);
}

bool SwarmNode::registerIRSensor(const char* name, uint8_t pin, bool pullup) {
    return registerDigitalInput(name, pin, pullup);
}

bool SwarmNode::registerDigitalInput(const char* name, uint8_t pin, bool pullup) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_DIGITAL_IN;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.pins[0] = pin;
    sens.pullup = pullup;
    SwarmHAL::setupSensor(sens);
    return true;
}

bool SwarmNode::registerAnalogInput(const char* name, uint8_t pin) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_ANALOG_IN;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.pins[0] = pin;
    SwarmHAL::setupSensor(sens);
    return true;
}

bool SwarmNode::registerBatteryVoltage(const char* name, uint8_t adcPin) {
    return registerAnalogInput(name, adcPin);
}

bool SwarmNode::registerTouchPin(const char* name, uint8_t touchPin) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_TOUCH;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.pins[0] = touchPin;
    SwarmHAL::setupSensor(sens);
    return true;
}

bool SwarmNode::registerDHT(const char* name, uint8_t pin, uint8_t model) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_DHT;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.pins[0] = pin;
    sens.sub_index = model;
    sens.value_count = 2;
    SwarmHAL::setupSensor(sens);
    return true;
}

bool SwarmNode::registerWiFiRSSI(const char* name) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_WIFI_RSSI;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    SwarmHAL::setupSensor(sens);
    return true;
}

// ============================================================================
// UNIVERSAL BUS PROTOCOLS & CUSTOM HARDWARE (I2C, SPI, UART, Custom)
// ============================================================================

bool SwarmNode::registerGenericI2C(const char* name, uint8_t i2cAddr, uint8_t regAddr, uint8_t numBytes,
                                   uint8_t sdaPin, uint8_t sclPin) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_GENERIC_I2C;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.i2c_addr = i2cAddr;
    sens.i2c_reg = regAddr;
    sens.i2c_len = numBytes;
    sens.pins[0] = sdaPin;
    sens.pins[1] = sclPin;
    SwarmHAL::setupSensor(sens);
    return true;
}

bool SwarmNode::registerI2CActuator(const char* name, uint8_t i2cAddr, uint8_t sdaPin, uint8_t sclPin) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_I2C_BUS;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.bus_addr = i2cAddr;
    act.pins[0] = sdaPin;
    act.pins[1] = sclPin;
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerSPISensor(const char* name, uint8_t csPin, uint8_t readReg, uint8_t numBytes,
                                  uint8_t sckPin, uint8_t misoPin, uint8_t mosiPin, uint32_t clockHz) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_SPI_DEVICE;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.pins[0] = csPin;
    sens.pins[1] = sckPin;
    sens.pins[2] = misoPin;
    sens.pins[3] = mosiPin;
    sens.i2c_reg = readReg;
    sens.i2c_len = numBytes;
    sens.bus_freq = clockHz;
    SwarmHAL::setupSensor(sens);
    return true;
}

bool SwarmNode::registerSPIActuator(const char* name, uint8_t csPin,
                                    uint8_t sckPin, uint8_t misoPin, uint8_t mosiPin, uint32_t clockHz) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_SPI_BUS;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.pins[0] = csPin;
    act.pins[1] = sckPin;
    act.pins[2] = misoPin;
    act.pins[3] = mosiPin;
    act.bus_freq = clockHz;
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerUARTSensor(const char* name, uint8_t rxPin, uint8_t txPin,
                                   uint32_t baud, uint8_t uartNum) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_UART_BUS;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.pins[0] = rxPin;
    sens.pins[1] = txPin;
    sens.i2c_addr = uartNum;
    sens.bus_freq = baud;
    SwarmHAL::setupSensor(sens);
    return true;
}

bool SwarmNode::registerUARTActuator(const char* name, uint8_t rxPin, uint8_t txPin,
                                     uint32_t baud, uint8_t uartNum) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_UART_BUS;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.pins[0] = rxPin;
    act.pins[1] = txPin;
    act.bus_addr = uartNum;
    act.bus_freq = baud;
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerCustomSensor(const char* name, SwarmCustomSensorFn readCallback) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS || !readCallback) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_CUSTOM;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.custom_fn = readCallback;
    sens.value_count = 1;
    return true;
}

bool SwarmNode::registerCustomSensorMulti(const char* name, SwarmCustomMultiSensorFn readMultiCallback) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_sensorCount >= SWARM_MAX_SENSORS || !readMultiCallback) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_CUSTOM_MULTI;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.custom_multi_fn = readMultiCallback;
    sens.value_count = 2;
    return true;
}

bool SwarmNode::registerCustomActuator(const char* name, SwarmCustomActuatorFn writeCallback) {
    if (!SwarmProtocol::validName(name)) return false;
    if (_actuatorCount >= SWARM_MAX_ACTUATORS || !writeCallback) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_CUSTOM;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.custom_fn = writeCallback;
    return true;
}

// ============================================================================
// BACKGROUND DAEMON STARTUP
// ============================================================================

#if defined(ESP32)
static void swarmEsp32Task(void* param) {
    SwarmNode* node = static_cast<SwarmNode*>(param);
    for (;;) {
        node->_backgroundTick();
        vTaskDelay(pdMS_TO_TICKS(2));
    }
}
#elif defined(ARDUINO_NANO_RP2040_CONNECT) || defined(ARDUINO_ARCH_MBED_RP2040)
static rtos::Thread* _rp2040Thread = nullptr;
static void swarmRp2040MbedTask() {
    for (;;) {
        if (_activeSwarmNode) {
            _activeSwarmNode->_backgroundTick();
        }
        rtos::ThisThread::sleep_for(std::chrono::milliseconds(2));
    }
}
#endif

void SwarmNode::start() {
    if (!_nodeId[0]) {
        Serial.println("[SwarmNode] Invalid node ID (use 1..19 letters, digits, '_' or '-').");
        return;
    }
    _udp.begin(_udpPort);
    _lastMasterPacketMs = millis();
    _activeSwarmNode = this;

    Serial.print("[SwarmNode] Registered ");
    Serial.print(_actuatorCount);
    Serial.print(" actuator(s) and ");
    Serial.print(_sensorCount);
    Serial.println(" sensor(s). Advertising to Linux Master...");

#if defined(ESP32)
    xTaskCreatePinnedToCore(
        swarmEsp32Task,
        "SwarmNodeTask",
        4096,
        this,
        2,
        NULL,
        0
    );
#elif defined(ARDUINO_NANO_RP2040_CONNECT) || defined(ARDUINO_ARCH_MBED_RP2040)
    _rp2040Thread = new rtos::Thread(osPriorityNormal, 4096);
    _rp2040Thread->start(mbed::callback(swarmRp2040MbedTask));
#endif
    // Pico W / UNO R4 WiFi / UNO WiFi Rev2 / Nano 33 IoT: driven by the auto-loop hook.
}

// ============================================================================
// CORE RUNTIME TICK (Network + Telemetry + Watchdog)
// ============================================================================

void SwarmNode::_backgroundTick() {
    _handleIncomingPacket();
    uint32_t now = millis();

    if (_masterConnected && (now - _lastMasterPacketMs > SWARM_WATCHDOG_MS)) {
        if (!_watchdogTripped) {
            _emergencyStopAll();
            _watchdogTripped = true;
            _watchdogTrips++;
            _lastCmdSeq = 0;
            Serial.println("[SwarmNode] WATCHDOG: Master timeout -> Motors stopped.");
        }
    }

    for (uint8_t i = 0; i < _actuatorCount; i++) {
        if (_actuators[i].pending && (int32_t)(now - _actuators[i].due_ms) >= 0) {
            _actuators[i].pending = false;
            if (_actuators[i].pending_lease_ms > 0) {
                _actuators[i].lease_active = true;
                _actuators[i].lease_due_ms = _actuators[i].due_ms + (uint32_t)_actuators[i].pending_lease_ms;
                _actuators[i].pending_lease_ms = 0;
            } else {
                _actuators[i].lease_active = false;
            }
            if (_actuators[i].type == ACT_SERVO) {
                _actuators[i].bus_addr = 1;
            }
            SwarmHAL::writeActuator(
                _actuators[i],
                _actuators[i].pending_v1,
                _actuators[i].pending_v2,
                _actuators[i].pending_data
            );
        }
        if (_actuators[i].lease_active && (int32_t)(now - _actuators[i].lease_due_ms) >= 0) {
            _stopActuator(_actuators[i]);
            _leaseExpirations++;
        }
    }

    if (_masterConnected && (now - _lastTelemetryMs >= SWARM_TELEMETRY_MS)) {
        _lastTelemetryMs = now;
        _sendTelemetry();
    }

    if (now - _lastHelloMs >= SWARM_HELLO_MS) {
        _lastHelloMs = now;
        _sendHelloBroadcast();
    }
}

void SwarmNode::_handleIncomingPacket() {
    int packetSize = _udp.parsePacket();
    if (packetSize <= 0) return;

    char buf[160];
    int len = _udp.read(buf, sizeof(buf) - 1);
    if (len <= 0) return;
    if (packetSize >= (int)sizeof(buf)) return;
    buf[len] = '\0';

    _processCommand(buf, _udp.remoteIP(), _udp.remotePort());
}

void SwarmNode::_processCommand(const char* json, IPAddress senderIP, uint16_t senderPort) {
    char cmd[16] = {0};
    if (!_extractString(json, "cmd", cmd, sizeof(cmd))) return;
    const char* numericFields[] = {"value", "state", "left", "right", "angle",
                                  "steps", "reg", "val", "v1", "v2", "pin", "pwm", "seq", "at_ms", "lease_ms"};
    for (uint8_t i = 0; i < sizeof(numericFields) / sizeof(numericFields[0]); ++i) {
        int16_t value;
        if (SwarmProtocol::field(json, numericFields[i]) &&
            !_extractInt(json, numericFields[i], value)) return;
    }

    int16_t seq = 0;
    bool hasSeq = (SwarmProtocol::field(json, "seq") != nullptr);
    if (hasSeq && (!_extractInt(json, "seq", seq) || seq < 1)) return;

    int16_t atMs = -1;
    bool hasAtMs = (SwarmProtocol::field(json, "at_ms") != nullptr);
    if (hasAtMs && (!_extractInt(json, "at_ms", atMs) || atMs < 0)) return;

    int16_t leaseMs = 0;
    bool hasLeaseMs = (SwarmProtocol::field(json, "lease_ms") != nullptr);
    if (hasLeaseMs && (!_extractInt(json, "lease_ms", leaseMs) || leaseMs < 1 || leaseMs > 30000)) return;

    if (!_masterConnected || _masterIP != senderIP || (senderPort > 0 && _masterPort != senderPort) || _watchdogTripped) {
        _lastCmdSeq = 0;
    }

    _masterIP = senderIP;
    if (senderPort > 0) _masterPort = senderPort;
    _masterConnected = true;
    _lastMasterPacketMs = millis();
    _watchdogTripped = false;

    if (strcmp(cmd, "PING") == 0) {
        if (hasSeq) SwarmProtocol::acceptSeq(seq, _lastCmdSeq);
        _sendTelemetry();
        return;
    }

    if (strcmp(cmd, "STOP") == 0) {
        if (hasSeq) SwarmProtocol::acceptSeq(seq, _lastCmdSeq);
        _emergencyStopAll();
        return;
    }

    if (strcmp(cmd, "ACT") == 0) {
        char targetName[16] = {0};
        if (!_extractString(json, "name", targetName, sizeof(targetName))) return;

        char dataPayload[32] = {0};
        if (SwarmProtocol::field(json, "data") &&
            !_extractString(json, "data", dataPayload, sizeof(dataPayload))) return;

        if (hasSeq && !SwarmProtocol::acceptSeq(seq, _lastCmdSeq)) {
            _droppedOutOfOrder++;
            return;
        }

        int16_t v1 = 0, v2 = 0;
        if (!_extractInt(json, "value", v1)) {
            if (!_extractInt(json, "state", v1)) {
                if (!_extractInt(json, "left", v1)) {
                    if (!_extractInt(json, "angle", v1)) {
                        if (!_extractInt(json, "steps", v1)) {
                            if (!_extractInt(json, "reg", v1)) {
                                _extractInt(json, "v1", v1);
                            }
                        }
                    }
                }
            }
        }
        if (!_extractInt(json, "right", v2)) {
            if (!_extractInt(json, "val", v2)) {
                _extractInt(json, "v2", v2);
            }
        }

        uint32_t nowMs = millis();
        int16_t deltaMs = hasAtMs ? SwarmProtocol::scheduleDelayMs(atMs, nowMs) : 0;

        for (uint8_t i = 0; i < _actuatorCount; i++) {
            if (strcmp(_actuators[i].name, targetName) == 0) {
                if (hasAtMs && deltaMs >= 1 && deltaMs <= 1000) {
                    _actuators[i].pending = true;
                    _actuators[i].due_ms = nowMs + (uint32_t)deltaMs;
                    _actuators[i].pending_v1 = v1;
                    _actuators[i].pending_v2 = v2;
                    _actuators[i].pending_lease_ms = hasLeaseMs ? (uint16_t)leaseMs : 0;
                    strncpy(_actuators[i].pending_data, dataPayload, sizeof(_actuators[i].pending_data) - 1);
                    _actuators[i].pending_data[sizeof(_actuators[i].pending_data) - 1] = '\0';
                } else {
                    _actuators[i].pending = false;
                    _actuators[i].pending_lease_ms = 0;
                    if (hasLeaseMs) {
                        _actuators[i].lease_active = true;
                        _actuators[i].lease_due_ms = nowMs + (uint32_t)leaseMs;
                    } else {
                        _actuators[i].lease_active = false;
                    }
                    if (_actuators[i].type == ACT_SERVO) {
                        _actuators[i].bus_addr = 1;
                    }
                    SwarmHAL::writeActuator(_actuators[i], v1, v2, dataPayload);
                }
                break;
            }
        }
        return;
    }

    if (strcmp(cmd, "PIN") == 0) {
        int16_t pin = -1, val = 0, mode = 0;
        if (_extractInt(json, "pin", pin) && pin >= 0 && pin <= 254) {
            if (hasSeq && !SwarmProtocol::acceptSeq(seq, _lastCmdSeq)) {
                _droppedOutOfOrder++;
                return;
            }
            _extractInt(json, "value", val);
            _extractInt(json, "pwm", mode);
            pinMode((uint8_t)pin, OUTPUT);
            if (mode > 0) {
                analogWrite((uint8_t)pin, constrain(val, 0, 255));
            } else {
                digitalWrite((uint8_t)pin, val > 0 ? HIGH : LOW);
            }
        }
    }
}

// ----------------------------------------------------------------------------
// Bounded JSON builders. Each append returns the new offset, or -1 if the text
// would not fit in the buffer (leaving `reserve` bytes free for closing brackets).
// ----------------------------------------------------------------------------
static const int SWARM_JSON_RESERVE = 4;  // room for closing "]}" / "}}" + '\0'

int SwarmNode::_appendf(char* buf, size_t cap, int offset, const char* fmt, ...) {
    if (offset < 0) return -1;
    int room = (int)cap - offset - SWARM_JSON_RESERVE;
    if (room <= 0) return -1;
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf + offset, (size_t)room, fmt, ap);
    va_end(ap);
    if (n < 0 || n >= room) {
        buf[offset] = '\0';  // roll back the partial write
        return -1;
    }
    return offset + n;
}

int SwarmNode::_appendFixed2(char* buf, size_t cap, int offset, const char* prefix, float v) {
    // Integer fixed-point formatting (avr-libc has no %f). Preserves the sign of
    // values in (-1, 0) and rejects NaN / Inf (not valid JSON).
    if (!(v == v) || v > 20000000.0f || v < -20000000.0f) v = 0.0f;
    long scaled = (long)(v * 100.0f + (v >= 0.0f ? 0.5f : -0.5f));
    bool neg = scaled < 0;
    unsigned long mag = (unsigned long)(neg ? -scaled : scaled);
    return _appendf(buf, cap, offset, "%s%s%lu.%02lu",
                    prefix, neg ? "-" : "", mag / 100UL, mag % 100UL);
}

void SwarmNode::_sendHelloBroadcast() {
    char msg[256];
    int offset = _appendf(msg, sizeof(msg), 0,
        "{\"type\":\"HELLO\",\"node\":\"%s\",\"board\":\"%s\",\"ip\":\"%s\",\"port\":%u,\"actuators\":[",
        _nodeId, SwarmHAL::boardName(), SwarmHAL::localIP().c_str(), (unsigned)_udpPort);
    if (offset < 0) return;

    for (uint8_t i = 0; i < _actuatorCount; i++) {
        int next = _appendf(msg, sizeof(msg), offset, "%s\"%s\"", (i > 0 ? "," : ""), _actuators[i].name);
        if (next < 0) break;
        offset = next;
    }
    int next = _appendf(msg, sizeof(msg), offset, "],\"sensors\":[");
    if (next < 0) {
        // No room for the sensor list: close the actuator array and finish.
        strcat(msg, "]}");
    } else {
        offset = next;
        for (uint8_t i = 0; i < _sensorCount; i++) {
            next = _appendf(msg, sizeof(msg), offset, "%s\"%s\"", (i > 0 ? "," : ""), _sensors[i].name);
            if (next < 0) break;
            offset = next;
        }
        strcat(msg, "]}");  // always fits thanks to SWARM_JSON_RESERVE
    }

    _udp.beginPacket(SwarmHAL::broadcastIP(), SWARM_DISCOVERY_PORT);
    _udp.write((const uint8_t*)msg, strlen(msg));
    _udp.endPacket();
}

void SwarmNode::_sendTelemetry() {
    if (!_masterConnected || _masterPort == 0) return;

    char msg[384];
    int offset = _appendf(msg, sizeof(msg), 0,
        "{\"type\":\"STATE\",\"node\":\"%s\",\"uptime_ms\":%lu",
        _nodeId, (unsigned long)millis());
    if (offset < 0) return;

    if (_lastCmdSeq > 0) {
        offset = _appendf(msg, sizeof(msg), offset, ",\"ack\":%d", (int)_lastCmdSeq);
        if (offset < 0) return;
    }
    if (_watchdogTrips > 0) {
        offset = _appendf(msg, sizeof(msg), offset, ",\"wd_trips\":%u", (unsigned)_watchdogTrips);
        if (offset < 0) return;
    }
    if (_leaseExpirations > 0) {
        offset = _appendf(msg, sizeof(msg), offset, ",\"lease_exp\":%u", (unsigned)_leaseExpirations);
        if (offset < 0) return;
    }
    if (_droppedOutOfOrder > 0) {
        offset = _appendf(msg, sizeof(msg), offset, ",\"seq_drop\":%u", (unsigned)_droppedOutOfOrder);
        if (offset < 0) return;
    }
    offset = _appendf(msg, sizeof(msg), offset, ",\"sensors\":{");
    if (offset < 0) return;

    bool first = true;
    for (uint8_t i = 0; i < _sensorCount; i++) {
        SwarmHAL::readSensor(_sensors[i]);
        uint8_t valueCount = _sensors[i].value_count;
        if (valueCount == 0) continue;
        if (valueCount > 6) valueCount = 6;

        int mark = offset;
        int o = _appendf(msg, sizeof(msg), offset, "%s\"%s\":", (first ? "" : ","), _sensors[i].name);

        if (valueCount == 1) {
            o = _appendFixed2(msg, sizeof(msg), o, "", _sensors[i].values[0]);
        } else {
            o = _appendf(msg, sizeof(msg), o, "[");
            for (uint8_t k = 0; k < valueCount && o >= 0; k++) {
                o = _appendFixed2(msg, sizeof(msg), o, (k > 0 ? "," : ""), _sensors[i].values[k]);
            }
            o = _appendf(msg, sizeof(msg), o, "]");
        }

        if (o < 0) {
            // This sensor does not fit: drop it (and any remaining ones) but keep valid JSON.
            msg[mark] = '\0';
            offset = mark;
            break;
        }
        offset = o;
        first = false;
    }
    strcat(msg, "}}");  // always fits thanks to SWARM_JSON_RESERVE

    _udp.beginPacket(_masterIP, _masterPort);
    _udp.write((const uint8_t*)msg, strlen(msg));
    _udp.endPacket();
}

void SwarmNode::_stopActuator(ActuatorDescriptor& act) {
    act.pending = false;
    act.pending_lease_ms = 0;
    act.lease_active = false;
    if (act.type == ACT_L298N ||
        act.type == ACT_DRV8833 ||
        act.type == ACT_MOTOR_2PIN ||
        act.type == ACT_STEPPER ||
        act.type == ACT_PWM_OUT ||
        act.type == ACT_DAC_OUT) {
        SwarmHAL::writeActuator(act, 0, 0, "");
    } else if (act.type == ACT_SERVO) {
        act.bus_addr = 0;
    } else if (act.type == ACT_CUSTOM) {
        SwarmHAL::writeActuator(act, 0, 0, "STOP");
    }
}

void SwarmNode::_emergencyStopAll() {
    for (uint8_t i = 0; i < _actuatorCount; i++) {
        _stopActuator(_actuators[i]);
    }
}

bool SwarmNode::_extractString(const char* json, const char* key, char* outBuf, size_t maxLen) {
    return SwarmProtocol::extractString(json, key, outBuf, maxLen);
}

bool SwarmNode::_extractInt(const char* json, const char* key, int16_t& outVal) {
    return SwarmProtocol::extractInt(json, key, outVal);
}
