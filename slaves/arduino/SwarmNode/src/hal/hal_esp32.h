#ifndef HAL_ESP32_H
#define HAL_ESP32_H

#if defined(ESP32)

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include <SPI.h>
#include "../SwarmTypes.h"

namespace SwarmHAL {

    // Hardware Interrupt Quadrature Encoder State (Up to 4 encoders)
    static volatile int32_t _encTicks[SWARM_MAX_ENCODERS] = {0, 0, 0, 0};
    static uint8_t _encPinA[SWARM_MAX_ENCODERS] = {0, 0, 0, 0};
    static uint8_t _encPinB[SWARM_MAX_ENCODERS] = {0, 0, 0, 0};
    static bool _wireInitialized = false;
    static bool _spiInitialized = false;

    inline void IRAM_ATTR _isrEnc0() {
        int a = digitalRead(_encPinA[0]);
        int b = (_encPinB[0] != 255) ? digitalRead(_encPinB[0]) : LOW;
        if (_encPinB[0] == 255) { _encTicks[0]++; }
        else { _encTicks[0] += (a == b) ? 1 : -1; }
    }
    inline void IRAM_ATTR _isrEnc1() {
        int a = digitalRead(_encPinA[1]);
        int b = (_encPinB[1] != 255) ? digitalRead(_encPinB[1]) : LOW;
        if (_encPinB[1] == 255) { _encTicks[1]++; }
        else { _encTicks[1] += (a == b) ? 1 : -1; }
    }
    inline void IRAM_ATTR _isrEnc2() {
        int a = digitalRead(_encPinA[2]);
        int b = (_encPinB[2] != 255) ? digitalRead(_encPinB[2]) : LOW;
        if (_encPinB[2] == 255) { _encTicks[2]++; }
        else { _encTicks[2] += (a == b) ? 1 : -1; }
    }
    inline void IRAM_ATTR _isrEnc3() {
        int a = digitalRead(_encPinA[3]);
        int b = (_encPinB[3] != 255) ? digitalRead(_encPinB[3]) : LOW;
        if (_encPinB[3] == 255) { _encTicks[3]++; }
        else { _encTicks[3] += (a == b) ? 1 : -1; }
    }

    inline const char* boardName() {
        return "ESP32";
    }

    inline void initI2C(int sda = -1, int scl = -1) {
        if (!_wireInitialized) {
            if (sda >= 0 && scl >= 0 && sda != 255 && scl != 255) {
                Wire.begin(sda, scl, 400000UL);
            } else {
                Wire.begin();
                Wire.setClock(400000UL);
            }
            _wireInitialized = true;
        }
    }

    inline void initSPI(int sck = -1, int miso = -1, int mosi = -1) {
        if (!_spiInitialized) {
            if (sck >= 0 && miso >= 0 && mosi >= 0 && sck != 255 && miso != 255 && mosi != 255) {
                SPI.begin(sck, miso, mosi);
            } else {
                SPI.begin();
            }
            _spiInitialized = true;
        }
    }

    inline HardwareSerial* getUART(uint8_t uartNum) {
        if (uartNum == 1) return &Serial1;
        return &Serial2;
    }

    // Minimal SX1276/SX1278 SPI Register Helpers for Built-In LoRa Support
    inline uint8_t loraReadReg(uint8_t csPin, uint8_t reg) {
        SPI.beginTransaction(SPISettings(8000000UL, MSBFIRST, SPI_MODE0));
        digitalWrite(csPin, LOW);
        SPI.transfer(reg & 0x7F);
        uint8_t val = SPI.transfer(0x00);
        digitalWrite(csPin, HIGH);
        SPI.endTransaction();
        return val;
    }

    inline void loraWriteReg(uint8_t csPin, uint8_t reg, uint8_t val) {
        SPI.beginTransaction(SPISettings(8000000UL, MSBFIRST, SPI_MODE0));
        digitalWrite(csPin, LOW);
        SPI.transfer(reg | 0x80);
        SPI.transfer(val);
        digitalWrite(csPin, HIGH);
        SPI.endTransaction();
    }

    inline void initLoRaSX127x(uint8_t csPin, uint8_t rstPin, uint32_t freqHz,
                               uint8_t sck, uint8_t miso, uint8_t mosi) {
        pinMode(csPin, OUTPUT);
        digitalWrite(csPin, HIGH);
        if (rstPin != 255) {
            pinMode(rstPin, OUTPUT);
            digitalWrite(rstPin, LOW);
            delay(10);
            digitalWrite(rstPin, HIGH);
            delay(10);
        }
        initSPI(sck, miso, mosi);

        // Put SX127x into LoRa Sleep mode (RegOpMode 0x01 = 0x80)
        loraWriteReg(csPin, 0x01, 0x80);
        delay(5);

        // Set Carrier Frequency (FRF = (freqHz << 19) / 32000000)
        uint64_t frf = ((uint64_t)freqHz << 19) / 32000000ULL;
        loraWriteReg(csPin, 0x06, (uint8_t)(frf >> 16));
        loraWriteReg(csPin, 0x07, (uint8_t)(frf >> 8));
        loraWriteReg(csPin, 0x08, (uint8_t)(frf >> 0));

        // Base FIFO pointers
        loraWriteReg(csPin, 0x0E, 0x00); // RegFifoTxBaseAddr
        loraWriteReg(csPin, 0x0F, 0x00); // RegFifoRxBaseAddr

        // Put into Continuous RX Mode (0x85) so it listens passively until TX
        loraWriteReg(csPin, 0x01, 0x85);
    }

    inline bool connectNetwork(const char* ssid, const char* password, uint32_t timeout_ms = 15000) {
        WiFi.mode(WIFI_STA);
        WiFi.setSleep(false); // Low-latency UDP mode (<5ms jitter)
        WiFi.begin(ssid, password);

        uint32_t start = millis();
        while (WiFi.status() != WL_CONNECTED) {
            if (millis() - start > timeout_ms) {
                return false;
            }
            delay(250);
        }
        return true;
    }

    inline String localIP() {
        return WiFi.localIP().toString();
    }

    inline IPAddress broadcastIP() {
        IPAddress ip = WiFi.localIP();
        IPAddress subnet = WiFi.subnetMask();
        IPAddress bcast;
        for (int i = 0; i < 4; i++) {
            bcast[i] = ip[i] | (~subnet[i]);
        }
        return bcast;
    }

    // ========================================================================
    // ACTUATOR SETUP
    // ========================================================================
    inline void setupActuator(ActuatorDescriptor& act) {
        switch (act.type) {
            case ACT_L298N:
                for (int i = 0; i < 6; i++) {
                    pinMode(act.pins[i], OUTPUT);
                    digitalWrite(act.pins[i], LOW);
                }
                break;

            case ACT_DRV8833:
                for (int i = 0; i < 4; i++) {
                    pinMode(act.pins[i], OUTPUT);
                    digitalWrite(act.pins[i], LOW);
                }
                break;

            case ACT_MOTOR_2PIN:
                pinMode(act.pins[0], OUTPUT);
                pinMode(act.pins[1], OUTPUT);
                digitalWrite(act.pins[0], LOW);
                digitalWrite(act.pins[1], LOW);
                break;

            case ACT_SERVO:
                pinMode(act.pins[0], OUTPUT);
                digitalWrite(act.pins[0], LOW);
                break;

            case ACT_STEPPER:
                pinMode(act.pins[0], OUTPUT);
                pinMode(act.pins[1], OUTPUT);
                digitalWrite(act.pins[0], LOW);
                digitalWrite(act.pins[1], LOW);
                if (act.pins[2] != 255) {
                    pinMode(act.pins[2], OUTPUT);
                    digitalWrite(act.pins[2], LOW);
                }
                break;

            case ACT_DIGITAL_OUT:
            case ACT_PWM_OUT:
            case ACT_DAC_OUT:
                pinMode(act.pins[0], OUTPUT);
                digitalWrite(act.pins[0], LOW);
                break;

            case ACT_UART_BUS: {
                // pins[0]=RX, pins[1]=TX, pins[2]=M0 (optional LoRa), pins[3]=M1 (optional LoRa)
                if (act.pins[2] != 255) { pinMode(act.pins[2], OUTPUT); digitalWrite(act.pins[2], LOW); }
                if (act.pins[3] != 255) { pinMode(act.pins[3], OUTPUT); digitalWrite(act.pins[3], LOW); }
                HardwareSerial* serial = getUART(act.bus_addr);
                uint32_t baud = (act.bus_freq > 0) ? act.bus_freq : 9600;
                serial->begin(baud, SERIAL_8N1, (int8_t)act.pins[0], (int8_t)act.pins[1]);
                break;
            }

            case ACT_I2C_BUS:
                initI2C(act.pins[0], act.pins[1]);
                break;

            case ACT_SPI_BUS:
                // pins[0]=CS, pins[1]=SCK, pins[2]=MISO, pins[3]=MOSI
                pinMode(act.pins[0], OUTPUT);
                digitalWrite(act.pins[0], HIGH);
                initSPI(act.pins[1], act.pins[2], act.pins[3]);
                break;

            case ACT_LORA_SPI:
                // pins[0]=CS, pins[1]=RST, pins[2]=IRQ, pins[3]=SCK, pins[4]=MISO, pins[5]=MOSI
                initLoRaSX127x(act.pins[0], act.pins[1],
                               (act.bus_freq > 0) ? act.bus_freq : 868000000UL,
                               act.pins[3], act.pins[4], act.pins[5]);
                break;

            default:
                break;
        }
    }

    // ========================================================================
    // SENSOR SETUP
    // ========================================================================
    inline void setupSensor(SensorDescriptor& sens) {
        switch (sens.type) {
            case SENS_ULTRASONIC:
                pinMode(sens.pins[0], OUTPUT);
                digitalWrite(sens.pins[0], LOW);
                pinMode(sens.pins[1], INPUT);
                break;

            case SENS_DIGITAL_IN:
                pinMode(sens.pins[0], sens.pullup ? INPUT_PULLUP : INPUT);
                break;

            case SENS_ANALOG_IN:
                pinMode(sens.pins[0], INPUT);
                break;

            case SENS_ENCODER_QUAD:
            case SENS_TACHOMETER: {
                uint8_t idx = sens.sub_index;
                if (idx < SWARM_MAX_ENCODERS) {
                    _encPinA[idx] = sens.pins[0];
                    _encPinB[idx] = (sens.type == SENS_ENCODER_QUAD) ? sens.pins[1] : 255;
                    _encTicks[idx] = 0;
                    pinMode(_encPinA[idx], INPUT_PULLUP);
                    if (_encPinB[idx] != 255) {
                        pinMode(_encPinB[idx], INPUT_PULLUP);
                    }
                    void (*isr)() = nullptr;
                    if (idx == 0) isr = _isrEnc0;
                    else if (idx == 1) isr = _isrEnc1;
                    else if (idx == 2) isr = _isrEnc2;
                    else if (idx == 3) isr = _isrEnc3;
                    if (isr) {
                        attachInterrupt(digitalPinToInterrupt(_encPinA[idx]), isr, CHANGE);
                    }
                }
                break;
            }

            case SENS_DHT:
                pinMode(sens.pins[0], INPUT_PULLUP);
                break;

            case SENS_MPU6050: {
                initI2C(sens.pins[0], sens.pins[1]);
                Wire.beginTransmission(sens.i2c_addr);
                Wire.write(0x6B);
                Wire.write(0x00);
                Wire.endTransmission();
                break;
            }

            case SENS_INA219:
            case SENS_GENERIC_I2C:
            case SENS_VL53L0X:
                initI2C(sens.pins[0], sens.pins[1]);
                break;

            case SENS_SPI_DEVICE:
                // pins[0]=CS, pins[1]=SCK, pins[2]=MISO, pins[3]=MOSI
                pinMode(sens.pins[0], OUTPUT);
                digitalWrite(sens.pins[0], HIGH);
                initSPI(sens.pins[1], sens.pins[2], sens.pins[3]);
                break;

            case SENS_UART_BUS: {
                HardwareSerial* serial = getUART(sens.i2c_addr);
                uint32_t baud = (sens.bus_freq > 0) ? sens.bus_freq : 9600;
                serial->begin(baud, SERIAL_8N1, (int8_t)sens.pins[0], (int8_t)sens.pins[1]);
                break;
            }

            case SENS_LORA_SPI:
                initLoRaSX127x(sens.pins[0], sens.pins[1],
                               (sens.bus_freq > 0) ? sens.bus_freq : 868000000UL,
                               sens.pins[3], sens.pins[4], sens.pins[5]);
                break;

            default:
                break;
        }
    }

    // ========================================================================
    // ACTUATOR EXECUTION HELPERS
    // ========================================================================
    inline void driveHBridge3Pin(uint8_t ena, uint8_t in1, uint8_t in2, int16_t speed) {
        int16_t s = constrain(speed, -255, 255);
        if (s > 0) {
            digitalWrite(in1, HIGH);
            digitalWrite(in2, LOW);
            analogWrite(ena, s);
        } else if (s < 0) {
            digitalWrite(in1, LOW);
            digitalWrite(in2, HIGH);
            analogWrite(ena, -s);
        } else {
            digitalWrite(in1, LOW);
            digitalWrite(in2, LOW);
            analogWrite(ena, 0);
        }
    }

    inline void driveHBridge2Pin(uint8_t in1, uint8_t in2, int16_t speed) {
        int16_t s = constrain(speed, -255, 255);
        if (s > 0) {
            analogWrite(in1, s);
            analogWrite(in2, 0);
        } else if (s < 0) {
            analogWrite(in1, 0);
            analogWrite(in2, -s);
        } else {
            analogWrite(in1, 0);
            analogWrite(in2, 0);
        }
    }

    inline void writeActuator(ActuatorDescriptor& act, int16_t v1, int16_t v2, const char* dataPayload = "") {
        act.val1 = v1;
        act.val2 = v2;

        switch (act.type) {
            case ACT_L298N:
                driveHBridge3Pin(act.pins[0], act.pins[1], act.pins[2], v1);
                driveHBridge3Pin(act.pins[3], act.pins[4], act.pins[5], v2);
                break;

            case ACT_DRV8833:
                driveHBridge2Pin(act.pins[0], act.pins[1], v1);
                driveHBridge2Pin(act.pins[2], act.pins[3], v2);
                break;

            case ACT_MOTOR_2PIN:
                driveHBridge2Pin(act.pins[0], act.pins[1], v1);
                break;

            case ACT_SERVO: {
                int16_t angle = constrain(v1, 0, 180);
                uint16_t pulseUs = map(angle, 0, 180, 500, 2400);
                for (int i = 0; i < 3; i++) {
                    digitalWrite(act.pins[0], HIGH);
                    delayMicroseconds(pulseUs);
                    digitalWrite(act.pins[0], LOW);
                    delayMicroseconds(20000 - pulseUs);
                }
                break;
            }

            case ACT_STEPPER: {
                int16_t steps = v1;
                uint16_t stepDelayUs = (v2 > 100) ? (uint16_t)v2 : 800;
                digitalWrite(act.pins[1], (steps >= 0) ? HIGH : LOW);
                int16_t count = abs(steps);
                if (count > 500) count = 500;
                for (int16_t i = 0; i < count; i++) {
                    digitalWrite(act.pins[0], HIGH);
                    delayMicroseconds(stepDelayUs);
                    digitalWrite(act.pins[0], LOW);
                    delayMicroseconds(stepDelayUs);
                }
                break;
            }

            case ACT_DIGITAL_OUT:
                digitalWrite(act.pins[0], v1 > 0 ? HIGH : LOW);
                break;

            case ACT_PWM_OUT:
                analogWrite(act.pins[0], constrain(v1, 0, 255));
                break;

            case ACT_DAC_OUT:
                #if defined(CONFIG_IDF_TARGET_ESP32)
                dacWrite(act.pins[0], constrain(v1, 0, 255));
                #else
                analogWrite(act.pins[0], constrain(v1, 0, 255));
                #endif
                break;

            case ACT_UART_BUS: {
                HardwareSerial* serial = getUART(act.bus_addr);
                if (dataPayload && dataPayload[0] != '\0') {
                    serial->println(dataPayload);
                } else {
                    serial->write((uint8_t)(v1 & 0xFF));
                }
                break;
            }

            case ACT_I2C_BUS: {
                // v1 = register address, v2 = byte value to write
                Wire.beginTransmission(act.bus_addr);
                Wire.write((uint8_t)(v1 & 0xFF));
                Wire.write((uint8_t)(v2 & 0xFF));
                Wire.endTransmission();
                break;
            }

            case ACT_SPI_BUS: {
                // v1 = register/command byte, v2 = value byte
                uint32_t clk = (act.bus_freq > 0) ? act.bus_freq : 1000000UL;
                SPI.beginTransaction(SPISettings(clk, MSBFIRST, SPI_MODE0));
                digitalWrite(act.pins[0], LOW);
                SPI.transfer((uint8_t)(v1 & 0xFF));
                SPI.transfer((uint8_t)(v2 & 0xFF));
                digitalWrite(act.pins[0], HIGH);
                SPI.endTransaction();
                break;
            }

            case ACT_LORA_SPI: {
                // Transmit packet over SX127x LoRa SPI
                uint8_t cs = act.pins[0];
                loraWriteReg(cs, 0x01, 0x81); // Standby mode
                loraWriteReg(cs, 0x0D, 0x00); // FIFO addr ptr = 0
                uint8_t len = 0;
                if (dataPayload && dataPayload[0] != '\0') {
                    while (dataPayload[len] != '\0' && len < 64) {
                        loraWriteReg(cs, 0x00, (uint8_t)dataPayload[len]);
                        len++;
                    }
                } else {
                    loraWriteReg(cs, 0x00, (uint8_t)((v1 >> 8) & 0xFF));
                    loraWriteReg(cs, 0x00, (uint8_t)(v1 & 0xFF));
                    len = 2;
                }
                loraWriteReg(cs, 0x22, len);  // RegPayloadLength
                loraWriteReg(cs, 0x01, 0x83); // TX Mode
                delay(25);
                loraWriteReg(cs, 0x12, 0xFF); // Clear IRQ flags
                loraWriteReg(cs, 0x01, 0x85); // Return to Continuous RX
                break;
            }

            case ACT_CUSTOM: {
                if (act.custom_fn) {
                    act.custom_fn(v1, v2, dataPayload ? dataPayload : "");
                }
                break;
            }

            default:
                break;
        }
    }

    // ========================================================================
    // SENSOR READING (Supports 1-value, Multi-Axis, Bus & Custom Sensors)
    // ========================================================================
    inline void readSensor(SensorDescriptor& sens) {
        switch (sens.type) {
            case SENS_ULTRASONIC: {
                uint8_t trig = sens.pins[0];
                uint8_t echo = sens.pins[1];
                digitalWrite(trig, LOW);
                delayMicroseconds(2);
                digitalWrite(trig, HIGH);
                delayMicroseconds(10);
                digitalWrite(trig, LOW);
                unsigned long duration = pulseIn(echo, HIGH, 15000UL);
                sens.values[0] = (duration == 0) ? -1.0f : ((duration * 0.0343f) * 0.5f);
                sens.value_count = 1;
                break;
            }

            case SENS_DIGITAL_IN: {
                int raw = digitalRead(sens.pins[0]);
                sens.values[0] = sens.pullup ? (raw == LOW ? 1.0f : 0.0f) : (raw == HIGH ? 1.0f : 0.0f);
                sens.value_count = 1;
                break;
            }

            case SENS_ANALOG_IN:
                sens.values[0] = (float)analogRead(sens.pins[0]);
                sens.value_count = 1;
                break;

            case SENS_TOUCH:
                #if defined(CONFIG_IDF_TARGET_ESP32) || defined(CONFIG_IDF_TARGET_ESP32S2) || defined(CONFIG_IDF_TARGET_ESP32S3)
                sens.values[0] = (float)touchRead(sens.pins[0]);
                #else
                sens.values[0] = (float)digitalRead(sens.pins[0]);
                #endif
                sens.value_count = 1;
                break;

            case SENS_ENCODER_QUAD:
            case SENS_TACHOMETER: {
                uint8_t idx = sens.sub_index;
                sens.values[0] = (idx < SWARM_MAX_ENCODERS) ? (float)_encTicks[idx] : 0.0f;
                sens.value_count = 1;
                break;
            }

            case SENS_DHT: {
                uint8_t pin = sens.pins[0];
                uint8_t data[5] = {0, 0, 0, 0, 0};
                pinMode(pin, OUTPUT);
                digitalWrite(pin, LOW);
                delay(18);
                digitalWrite(pin, HIGH);
                delayMicroseconds(30);
                pinMode(pin, INPUT_PULLUP);

                if (pulseIn(pin, LOW, 1000UL) > 0) {
                    for (int i = 0; i < 40; i++) {
                        unsigned long highUs = pulseIn(pin, HIGH, 200UL);
                        data[i / 8] <<= 1;
                        if (highUs > 40) data[i / 8] |= 1;
                    }
                    if (((data[0] + data[1] + data[2] + data[3]) & 0xFF) == data[4]) {
                        if (sens.sub_index == 11) {
                            sens.values[0] = (float)data[2];
                            sens.values[1] = (float)data[0];
                        } else {
                            sens.values[1] = ((data[0] << 8) | data[1]) * 0.1f;
                            int16_t rawT = ((data[2] & 0x7F) << 8) | data[3];
                            sens.values[0] = rawT * ((data[2] & 0x80) ? -0.1f : 0.1f);
                        }
                    }
                }
                sens.value_count = 2;
                break;
            }

            case SENS_MPU6050: {
                Wire.beginTransmission(sens.i2c_addr);
                Wire.write(0x3B);
                if (Wire.endTransmission(false) == 0 && Wire.requestFrom((int)sens.i2c_addr, 14) == 14) {
                    int16_t ax = (Wire.read() << 8) | Wire.read();
                    int16_t ay = (Wire.read() << 8) | Wire.read();
                    int16_t az = (Wire.read() << 8) | Wire.read();
                    Wire.read(); Wire.read();
                    int16_t gx = (Wire.read() << 8) | Wire.read();
                    int16_t gy = (Wire.read() << 8) | Wire.read();
                    int16_t gz = (Wire.read() << 8) | Wire.read();
                    sens.values[0] = ax / 16384.0f;
                    sens.values[1] = ay / 16384.0f;
                    sens.values[2] = az / 16384.0f;
                    sens.values[3] = gx / 131.0f;
                    sens.values[4] = gy / 131.0f;
                    sens.values[5] = gz / 131.0f;
                }
                sens.value_count = 6;
                break;
            }

            case SENS_INA219: {
                Wire.beginTransmission(sens.i2c_addr);
                Wire.write(0x02);
                if (Wire.endTransmission(false) == 0 && Wire.requestFrom((int)sens.i2c_addr, 2) == 2) {
                    uint16_t rawBus = (Wire.read() << 8) | Wire.read();
                    sens.values[0] = ((rawBus >> 3) * 4) * 0.001f;
                }
                Wire.beginTransmission(sens.i2c_addr);
                Wire.write(0x01);
                if (Wire.endTransmission(false) == 0 && Wire.requestFrom((int)sens.i2c_addr, 2) == 2) {
                    int16_t rawShunt = (Wire.read() << 8) | Wire.read();
                    sens.values[1] = rawShunt * 0.1f;
                }
                sens.value_count = 2;
                break;
            }

            case SENS_GENERIC_I2C:
            case SENS_VL53L0X: {
                Wire.beginTransmission(sens.i2c_addr);
                Wire.write(sens.i2c_reg);
                uint8_t n = constrain(sens.i2c_len, (uint8_t)1, (uint8_t)4);
                if (Wire.endTransmission(false) == 0 && Wire.requestFrom((int)sens.i2c_addr, (int)n) == n) {
                    uint32_t combined = 0;
                    for (uint8_t b = 0; b < n; b++) {
                        combined = (combined << 8) | Wire.read();
                    }
                    sens.values[0] = (float)combined;
                }
                sens.value_count = 1;
                break;
            }

            case SENS_SPI_DEVICE: {
                uint32_t clk = (sens.bus_freq > 0) ? sens.bus_freq : 1000000UL;
                uint8_t n = constrain(sens.i2c_len, (uint8_t)1, (uint8_t)4);
                SPI.beginTransaction(SPISettings(clk, MSBFIRST, SPI_MODE0));
                digitalWrite(sens.pins[0], LOW);
                SPI.transfer(sens.i2c_reg);
                uint32_t combined = 0;
                for (uint8_t b = 0; b < n; b++) {
                    combined = (combined << 8) | SPI.transfer(0x00);
                }
                digitalWrite(sens.pins[0], HIGH);
                SPI.endTransaction();
                sens.values[0] = (float)combined;
                sens.value_count = 1;
                break;
            }

            case SENS_UART_BUS: {
                HardwareSerial* serial = getUART(sens.i2c_addr);
                if (serial->available() > 0) {
                    String line = serial->readStringUntil('\n');
                    line.trim();
                    if (line.length() > 0) {
                        sens.values[0] = line.toFloat();
                    }
                }
                sens.value_count = 1;
                break;
            }

            case SENS_LORA_SPI: {
                // Check SX127x RegIrqFlags (0x12) for RxDone (0x40)
                uint8_t cs = sens.pins[0];
                uint8_t irq = loraReadReg(cs, 0x12);
                if (irq & 0x40) {
                    uint8_t len = loraReadReg(cs, 0x13); // RegRxNbBytes
                    uint8_t fifoAddr = loraReadReg(cs, 0x10); // RegFifoRxCurrentAddr
                    loraWriteReg(cs, 0x0D, fifoAddr);
                    char rxBuf[32] = {0};
                    for (uint8_t i = 0; i < len && i < 31; i++) {
                        rxBuf[i] = (char)loraReadReg(cs, 0x00);
                    }
                    loraWriteReg(cs, 0x12, 0xFF); // Clear IRQ
                    sens.values[0] = atof(rxBuf); // Numeric payload or first bytes
                    int rssiRaw = loraReadReg(cs, 0x1B);
                    sens.values[1] = (float)(rssiRaw - 157); // Packet RSSI in dBm
                }
                sens.value_count = 2;
                break;
            }

            case SENS_CUSTOM: {
                if (sens.custom_fn) {
                    sens.values[0] = sens.custom_fn();
                }
                sens.value_count = 1;
                break;
            }

            case SENS_CUSTOM_MULTI: {
                if (sens.custom_multi_fn) {
                    uint8_t count = 1;
                    sens.custom_multi_fn(sens.values, count);
                    sens.value_count = constrain(count, (uint8_t)1, (uint8_t)6);
                }
                break;
            }

            case SENS_WIFI_RSSI:
                sens.values[0] = (float)WiFi.RSSI();
                sens.value_count = 1;
                break;

            default:
                break;
        }
    }

} // namespace SwarmHAL

#endif // ESP32
#endif // HAL_ESP32_H
