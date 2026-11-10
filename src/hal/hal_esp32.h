#ifndef HAL_ESP32_H
#define HAL_ESP32_H

#if defined(ESP32)

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include <SPI.h>
#if __has_include(<ESP32Servo.h>)
  #include <ESP32Servo.h>
  #define SWARM_HAS_ESP32SERVO 1
#else
  #define SWARM_HAS_ESP32SERVO 0
#endif
#include "../SwarmTypes.h"

namespace SwarmHAL {

    #if SWARM_HAS_ESP32SERVO
    inline Servo& espServo(uint8_t pin) {
        static Servo servos[4];
        static uint8_t pins[4] = {255, 255, 255, 255};
        static bool timersAllocated = false;
        if (!timersAllocated) {
            ESP32PWM::allocateTimer(0);
            ESP32PWM::allocateTimer(1);
            ESP32PWM::allocateTimer(2);
            ESP32PWM::allocateTimer(3);
            timersAllocated = true;
        }
        for (int i = 0; i < 4; i++) {
            if (pins[i] == pin) return servos[i];
            if (pins[i] == 255) {
                pins[i] = pin;
                servos[i].setPeriodHertz(50);
                servos[i].attach(pin, 500, 2400);
                return servos[i];
            }
        }
        return servos[0];
    }
    #endif

    // Hardware Interrupt Quadrature Encoder State (Up to 4 encoders)
    inline volatile int32_t& encTicks(uint8_t i) {
        static volatile int32_t ticks[SWARM_MAX_ENCODERS] = {0, 0, 0, 0};
        return ticks[i];
    }
    inline uint8_t& encPinA(uint8_t i) {
        static uint8_t pinA[SWARM_MAX_ENCODERS] = {0, 0, 0, 0};
        return pinA[i];
    }
    inline uint8_t& encPinB(uint8_t i) {
        static uint8_t pinB[SWARM_MAX_ENCODERS] = {0, 0, 0, 0};
        return pinB[i];
    }
    inline bool& wireInitialized() {
        static bool init = false;
        return init;
    }
    inline bool& spiInitialized() {
        static bool init = false;
        return init;
    }

    inline void _isrEnc0() {
        int a = digitalRead(encPinA(0));
        int b = (encPinB(0) != 255) ? digitalRead(encPinB(0)) : LOW;
        if (encPinB(0) == 255) { encTicks(0)++; }
        else { encTicks(0) += (a == b) ? 1 : -1; }
    }
    inline void _isrEnc1() {
        int a = digitalRead(encPinA(1));
        int b = (encPinB(1) != 255) ? digitalRead(encPinB(1)) : LOW;
        if (encPinB(1) == 255) { encTicks(1)++; }
        else { encTicks(1) += (a == b) ? 1 : -1; }
    }
    inline void _isrEnc2() {
        int a = digitalRead(encPinA(2));
        int b = (encPinB(2) != 255) ? digitalRead(encPinB(2)) : LOW;
        if (encPinB(2) == 255) { encTicks(2)++; }
        else { encTicks(2) += (a == b) ? 1 : -1; }
    }
    inline void _isrEnc3() {
        int a = digitalRead(encPinA(3));
        int b = (encPinB(3) != 255) ? digitalRead(encPinB(3)) : LOW;
        if (encPinB(3) == 255) { encTicks(3)++; }
        else { encTicks(3) += (a == b) ? 1 : -1; }
    }

    inline const char* boardName() {
        return "ESP32";
    }

    inline void initI2C(int sda = -1, int scl = -1) {
        if (!wireInitialized()) {
            if (sda >= 0 && scl >= 0 && sda != 255 && scl != 255) {
                Wire.begin(sda, scl, 400000UL);
            } else {
                Wire.begin();
                Wire.setClock(400000UL);
            }
            wireInitialized() = true;
        }
    }

    inline void initSPI(int sck = -1, int miso = -1, int mosi = -1) {
        if (!spiInitialized()) {
            if (sck >= 0 && miso >= 0 && mosi >= 0 && sck != 255 && miso != 255 && mosi != 255) {
                SPI.begin(sck, miso, mosi);
            } else {
                SPI.begin();
            }
            spiInitialized() = true;
        }
    }

    inline HardwareSerial* getUART(uint8_t uartNum) {
        if (uartNum == 1) return &Serial1;
        return &Serial2;
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
                #if SWARM_HAS_ESP32SERVO
                espServo(act.pins[0]).write(90);
                #else
                pinMode(act.pins[0], OUTPUT);
                digitalWrite(act.pins[0], LOW);
                #endif
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
                HardwareSerial* serial = getUART(act.bus_addr);
                uint32_t baud = (act.bus_freq > 0) ? act.bus_freq : 9600;
                serial->begin(baud, SERIAL_8N1, (int8_t)act.pins[0], (int8_t)act.pins[1]);
                break;
            }

            case ACT_I2C_BUS:
                initI2C(act.pins[0], act.pins[1]);
                break;

            case ACT_SPI_BUS:
                pinMode(act.pins[0], OUTPUT);
                digitalWrite(act.pins[0], HIGH);
                initSPI(act.pins[1], act.pins[2], act.pins[3]);
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
                    encPinA(idx) = sens.pins[0];
                    encPinB(idx) = (sens.type == SENS_ENCODER_QUAD) ? sens.pins[1] : 255;
                    encTicks(idx) = 0;
                    pinMode(encPinA(idx), INPUT_PULLUP);
                    if (encPinB(idx) != 255) {
                        pinMode(encPinB(idx), INPUT_PULLUP);
                    }
                    void (*isr)() = nullptr;
                    if (idx == 0) isr = _isrEnc0;
                    else if (idx == 1) isr = _isrEnc1;
                    else if (idx == 2) isr = _isrEnc2;
                    else if (idx == 3) isr = _isrEnc3;
                    if (isr) {
                        attachInterrupt(digitalPinToInterrupt(encPinA(idx)), isr, CHANGE);
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

            case SENS_LSM6DSOX: {
                initI2C(sens.pins[0], sens.pins[1]);
                // Enable Accel (104 Hz, +/-2g -> CTRL1_XL 0x10 = 0x40)
                Wire.beginTransmission(sens.i2c_addr);
                Wire.write(0x10);
                Wire.write(0x40);
                Wire.endTransmission();
                // Enable Gyro (104 Hz, 250 dps -> CTRL2_G 0x11 = 0x40)
                Wire.beginTransmission(sens.i2c_addr);
                Wire.write(0x11);
                Wire.write(0x40);
                Wire.endTransmission();
                break;
            }

            case SENS_INA219:
            case SENS_GENERIC_I2C:
            case SENS_VL53L0X:
                initI2C(sens.pins[0], sens.pins[1]);
                break;

            case SENS_SPI_DEVICE:
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
                #if SWARM_HAS_ESP32SERVO
                espServo(act.pins[0]).write(angle);
                #else
                uint16_t pulseUs = map(angle, 0, 180, 500, 2400);
                digitalWrite(act.pins[0], HIGH);
                delayMicroseconds(pulseUs);
                digitalWrite(act.pins[0], LOW);
                #endif
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
                Wire.beginTransmission(act.bus_addr);
                Wire.write((uint8_t)(v1 & 0xFF));
                Wire.write((uint8_t)(v2 & 0xFF));
                Wire.endTransmission();
                break;
            }

            case ACT_SPI_BUS: {
                uint32_t clk = (act.bus_freq > 0) ? act.bus_freq : 1000000UL;
                SPI.beginTransaction(SPISettings(clk, MSBFIRST, SPI_MODE0));
                digitalWrite(act.pins[0], LOW);
                SPI.transfer((uint8_t)(v1 & 0xFF));
                SPI.transfer((uint8_t)(v2 & 0xFF));
                digitalWrite(act.pins[0], HIGH);
                SPI.endTransaction();
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
                sens.values[0] = (idx < SWARM_MAX_ENCODERS) ? (float)encTicks(idx) : 0.0f;
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

            case SENS_LSM6DSOX: {
                // Read 12 bytes starting at OUTX_L_G (0x22): Gyro (X,Y,Z) then Accel (X,Y,Z) little-endian
                Wire.beginTransmission(sens.i2c_addr);
                Wire.write(0x22);
                if (Wire.endTransmission(false) == 0 && Wire.requestFrom((int)sens.i2c_addr, 12) == 12) {
                    int16_t gx = Wire.read() | (Wire.read() << 8);
                    int16_t gy = Wire.read() | (Wire.read() << 8);
                    int16_t gz = Wire.read() | (Wire.read() << 8);
                    int16_t ax = Wire.read() | (Wire.read() << 8);
                    int16_t ay = Wire.read() | (Wire.read() << 8);
                    int16_t az = Wire.read() | (Wire.read() << 8);
                    sens.values[0] = ax * 0.000061f; // g (+/-2g scale)
                    sens.values[1] = ay * 0.000061f;
                    sens.values[2] = az * 0.000061f;
                    sens.values[3] = gx * 0.00875f;  // deg/s (250 dps scale)
                    sens.values[4] = gy * 0.00875f;
                    sens.values[5] = gz * 0.00875f;
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
