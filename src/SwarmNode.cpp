#include "SwarmNode.h"
#include <string.h>
#include <stdlib.h>

SwarmNode::SwarmNode(const char* node_id, uint16_t udp_port)
    : _udpPort(udp_port) {
    strncpy(_nodeId, node_id, sizeof(_nodeId) - 1);
    _nodeId[sizeof(_nodeId) - 1] = '\0';
}

bool SwarmNode::connectWiFi(const char* ssid, const char* password, uint32_t timeout_ms) {
    Serial.begin(115200);
    delay(100);
    Serial.println();
    Serial.print("[SwarmNode] Connecting node '");
    Serial.print(_nodeId);
    Serial.print("' to Wi-Fi: ");
    Serial.println(ssid);

    bool ok = SwarmHAL::connectNetwork(ssid, password, timeout_ms);
    if (ok) {
        Serial.print("[SwarmNode] Connected! IP: ");
        Serial.print(SwarmHAL::localIP());
        Serial.print(" | UDP Port: ");
        Serial.println(_udpPort);
    } else {
        Serial.println("[SwarmNode] ERROR: Wi-Fi connection timed out!");
    }
    return ok;
}

// ============================================================================
// STANDARD ACTUATOR REGISTRATION
// ============================================================================

bool SwarmNode::registerL298N(const char* name,
                              uint8_t ena, uint8_t in1, uint8_t in2,
                              uint8_t enb, uint8_t in3, uint8_t in4) {
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
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_SERVO;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.pins[0] = pin;
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerStepper(const char* name, uint8_t stepPin, uint8_t dirPin, uint8_t enPin) {
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
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_DIGITAL_OUT;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.pins[0] = pin;
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerPWMOutput(const char* name, uint8_t pin) {
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_PWM_OUT;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.pins[0] = pin;
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerDACOutput(const char* name, uint8_t pin) {
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

bool SwarmNode::registerINA219(const char* name, uint8_t i2cAddr, uint8_t sdaPin, uint8_t sclPin) {
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
    if (_sensorCount >= SWARM_MAX_SENSORS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_TOUCH;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.pins[0] = touchPin;
    SwarmHAL::setupSensor(sens);
    return true;
}

bool SwarmNode::registerDHT(const char* name, uint8_t pin, uint8_t model) {
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
    if (_sensorCount >= SWARM_MAX_SENSORS) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_WIFI_RSSI;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    SwarmHAL::setupSensor(sens);
    return true;
}

// ============================================================================
// UNIVERSAL BUS PROTOCOLS & CUSTOM HARDWARE (I2C, SPI, UART, LoRa, Custom)
// ============================================================================

bool SwarmNode::registerGenericI2C(const char* name, uint8_t i2cAddr, uint8_t regAddr, uint8_t numBytes,
                                   uint8_t sdaPin, uint8_t sclPin) {
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
    if (_actuatorCount >= SWARM_MAX_ACTUATORS) return false;
    ActuatorDescriptor& act = _actuators[_actuatorCount++];
    act.type = ACT_UART_BUS;
    strncpy(act.name, name, sizeof(act.name) - 1);
    act.pins[0] = rxPin;
    act.pins[1] = txPin;
    act.pins[2] = 255;
    act.pins[3] = 255;
    act.bus_addr = uartNum;
    act.bus_freq = baud;
    SwarmHAL::setupActuator(act);
    return true;
}

bool SwarmNode::registerLoRaUART(const char* name, uint8_t rxPin, uint8_t txPin,
                                 uint32_t baud, uint8_t m0Pin, uint8_t m1Pin, uint8_t uartNum) {
    // Registers BOTH a UART TX Actuator and UART RX Sensor under the given name
    if (_actuatorCount < SWARM_MAX_ACTUATORS) {
        ActuatorDescriptor& act = _actuators[_actuatorCount++];
        act.type = ACT_UART_BUS;
        strncpy(act.name, name, sizeof(act.name) - 1);
        act.pins[0] = rxPin;
        act.pins[1] = txPin;
        act.pins[2] = m0Pin;
        act.pins[3] = m1Pin;
        act.bus_addr = uartNum;
        act.bus_freq = baud;
        SwarmHAL::setupActuator(act);
    }
    if (_sensorCount < SWARM_MAX_SENSORS) {
        SensorDescriptor& sens = _sensors[_sensorCount++];
        sens.type = SENS_UART_BUS;
        strncpy(sens.name, name, sizeof(sens.name) - 1);
        sens.pins[0] = rxPin;
        sens.pins[1] = txPin;
        sens.i2c_addr = uartNum;
        sens.bus_freq = baud;
        return true;
    }
    return false;
}

bool SwarmNode::registerLoRaSPI(const char* name, uint8_t csPin, uint8_t rstPin, uint8_t irqPin,
                                uint32_t freqHz, uint8_t sckPin, uint8_t misoPin, uint8_t mosiPin) {
    // Registers SX1276/SX1278/RFM95 SPI LoRa as both TX Actuator and RX Sensor [val, rssi_dBm]
    if (_actuatorCount < SWARM_MAX_ACTUATORS) {
        ActuatorDescriptor& act = _actuators[_actuatorCount++];
        act.type = ACT_LORA_SPI;
        strncpy(act.name, name, sizeof(act.name) - 1);
        act.pins[0] = csPin; act.pins[1] = rstPin; act.pins[2] = irqPin;
        act.pins[3] = sckPin; act.pins[4] = misoPin; act.pins[5] = mosiPin;
        act.bus_freq = freqHz;
        SwarmHAL::setupActuator(act);
    }
    if (_sensorCount < SWARM_MAX_SENSORS) {
        SensorDescriptor& sens = _sensors[_sensorCount++];
        sens.type = SENS_LORA_SPI;
        strncpy(sens.name, name, sizeof(sens.name) - 1);
        sens.pins[0] = csPin; sens.pins[1] = rstPin; sens.pins[2] = irqPin;
        sens.pins[3] = sckPin; sens.pins[4] = misoPin; sens.pins[5] = mosiPin;
        sens.bus_freq = freqHz;
        sens.value_count = 2;
        return true;
    }
    return false;
}

bool SwarmNode::registerCustomSensor(const char* name, SwarmCustomSensorFn readCallback) {
    if (_sensorCount >= SWARM_MAX_SENSORS || !readCallback) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_CUSTOM;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.custom_fn = readCallback;
    sens.value_count = 1;
    return true;
}

bool SwarmNode::registerCustomSensorMulti(const char* name, SwarmCustomMultiSensorFn readMultiCallback) {
    if (_sensorCount >= SWARM_MAX_SENSORS || !readMultiCallback) return false;
    SensorDescriptor& sens = _sensors[_sensorCount++];
    sens.type = SENS_CUSTOM_MULTI;
    strncpy(sens.name, name, sizeof(sens.name) - 1);
    sens.custom_multi_fn = readMultiCallback;
    sens.value_count = 2;
    return true;
}

bool SwarmNode::registerCustomActuator(const char* name, SwarmCustomActuatorFn writeCallback) {
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
#endif

void SwarmNode::start() {
    _udp.begin(_udpPort);
    _lastMasterPacketMs = millis();

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
#endif
}

// ============================================================================
// CORE RUNTIME TICK (Network + Telemetry + Watchdog)
// ============================================================================

void SwarmNode::_backgroundTick() {
    uint32_t now = millis();

    _handleIncomingPacket();

    if (_masterConnected && (now - _lastMasterPacketMs > SWARM_WATCHDOG_MS)) {
        if (!_watchdogTripped) {
            _emergencyStopAll();
            _watchdogTripped = true;
            Serial.println("[SwarmNode] WATCHDOG: Master timeout -> Motors stopped.");
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

    char buf[256];
    int len = _udp.read(buf, sizeof(buf) - 1);
    if (len <= 0) return;
    buf[len] = '\0';

    _processCommand(buf, _udp.remoteIP(), _udp.remotePort());
}

void SwarmNode::_processCommand(const char* json, IPAddress senderIP, uint16_t senderPort) {
    char cmd[16] = {0};
    if (!_extractString(json, "cmd", cmd, sizeof(cmd))) return;

    _masterIP = senderIP;
    if (senderPort > 0) _masterPort = senderPort;
    _masterConnected = true;
    _lastMasterPacketMs = millis();
    _watchdogTripped = false;

    if (strcmp(cmd, "PING") == 0) {
        _sendTelemetry();
        return;
    }

    if (strcmp(cmd, "STOP") == 0) {
        _emergencyStopAll();
        return;
    }

    if (strcmp(cmd, "ACT") == 0) {
        char targetName[20] = {0};
        if (!_extractString(json, "name", targetName, sizeof(targetName))) return;

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

        char dataPayload[64] = {0};
        _extractString(json, "data", dataPayload, sizeof(dataPayload));

        for (uint8_t i = 0; i < _actuatorCount; i++) {
            if (strcmp(_actuators[i].name, targetName) == 0) {
                SwarmHAL::writeActuator(_actuators[i], v1, v2, dataPayload);
                break;
            }
        }
        return;
    }

    if (strcmp(cmd, "PIN") == 0) {
        int16_t pin = -1, val = 0, mode = 0;
        if (_extractInt(json, "pin", pin) && pin >= 0) {
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

void SwarmNode::_sendHelloBroadcast() {
    char msg[512];
    int offset = snprintf(msg, sizeof(msg),
        "{\"type\":\"HELLO\",\"node\":\"%s\",\"board\":\"%s\",\"ip\":\"%s\",\"port\":%u,\"actuators\":[",
        _nodeId, SwarmHAL::boardName(), SwarmHAL::localIP().c_str(), _udpPort);

    for (uint8_t i = 0; i < _actuatorCount; i++) {
        offset += snprintf(msg + offset, sizeof(msg) - offset,
            "%s\"%s\"", (i > 0 ? "," : ""), _actuators[i].name);
    }
    offset += snprintf(msg + offset, sizeof(msg) - offset, "],\"sensors\":[");

    for (uint8_t i = 0; i < _sensorCount; i++) {
        offset += snprintf(msg + offset, sizeof(msg) - offset,
            "%s\"%s\"", (i > 0 ? "," : ""), _sensors[i].name);
    }
    snprintf(msg + offset, sizeof(msg) - offset, "]}");

    _udp.beginPacket(SwarmHAL::broadcastIP(), SWARM_DISCOVERY_PORT);
    _udp.write((const uint8_t*)msg, strlen(msg));
    _udp.endPacket();
}

void SwarmNode::_sendTelemetry() {
    if (!_masterConnected || _masterPort == 0) return;

    char msg[640];
    int offset = snprintf(msg, sizeof(msg),
        "{\"type\":\"STATE\",\"node\":\"%s\",\"uptime_ms\":%lu,\"sensors\":{",
        _nodeId, (unsigned long)millis());

    for (uint8_t i = 0; i < _sensorCount; i++) {
        SwarmHAL::readSensor(_sensors[i]);
        if (_sensors[i].value_count <= 1) {
            offset += snprintf(msg + offset, sizeof(msg) - offset,
                "%s\"%s\":%.2f", (i > 0 ? "," : ""), _sensors[i].name, _sensors[i].values[0]);
        } else {
            offset += snprintf(msg + offset, sizeof(msg) - offset,
                "%s\"%s\":[", (i > 0 ? "," : ""), _sensors[i].name);
            for (uint8_t k = 0; k < _sensors[i].value_count; k++) {
                offset += snprintf(msg + offset, sizeof(msg) - offset,
                    "%s%.2f", (k > 0 ? "," : ""), _sensors[i].values[k]);
            }
            offset += snprintf(msg + offset, sizeof(msg) - offset, "]");
        }
    }
    snprintf(msg + offset, sizeof(msg) - offset, "}}");

    _udp.beginPacket(_masterIP, _masterPort);
    _udp.write((const uint8_t*)msg, strlen(msg));
    _udp.endPacket();
}

void SwarmNode::_emergencyStopAll() {
    for (uint8_t i = 0; i < _actuatorCount; i++) {
        if (_actuators[i].type == ACT_L298N ||
            _actuators[i].type == ACT_DRV8833 ||
            _actuators[i].type == ACT_MOTOR_2PIN ||
            _actuators[i].type == ACT_STEPPER) {
            SwarmHAL::writeActuator(_actuators[i], 0, 0);
        }
    }
}

bool SwarmNode::_extractString(const char* json, const char* key, char* outBuf, size_t maxLen) {
    char pattern[24];
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    const char* p = strstr(json, pattern);
    if (!p) return false;
    p = strchr(p + strlen(pattern), ':');
    if (!p) return false;
    p = strchr(p, '\"');
    if (!p) return false;
    p++;
    const char* end = strchr(p, '\"');
    if (!end) return false;
    size_t len = (size_t)(end - p);
    if (len >= maxLen) len = maxLen - 1;
    memcpy(outBuf, p, len);
    outBuf[len] = '\0';
    return true;
}

bool SwarmNode::_extractInt(const char* json, const char* key, int16_t& outVal) {
    char pattern[24];
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    const char* p = strstr(json, pattern);
    if (!p) return false;
    p = strchr(p + strlen(pattern), ':');
    if (!p) return false;
    p++;
    while (*p == ' ' || *p == '\\t') p++;
    outVal = (int16_t)atoi(p);
    return true;
}
