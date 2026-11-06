#ifndef SWARM_TYPES_H
#define SWARM_TYPES_H

#include <Arduino.h>

// Smaller tables for 8-bit AVR boards with limited SRAM (UNO WiFi Rev2: 6 KB)
#if defined(__AVR__)
  #define SWARM_MAX_ACTUATORS   6
  #define SWARM_MAX_SENSORS     8
  #define SWARM_MAX_ENCODERS    2
#else
  #define SWARM_MAX_ACTUATORS   14
  #define SWARM_MAX_SENSORS     18
  #define SWARM_MAX_ENCODERS    4
#endif

#define SWARM_DEFAULT_PORT    4210
#define SWARM_DISCOVERY_PORT  4211
#define SWARM_WATCHDOG_MS     500   // Auto-stop motors if Master is silent > 500ms
#define SWARM_TELEMETRY_MS    50    // 20 Hz sensor telemetry stream
#define SWARM_HELLO_MS        1000  // 1 Hz discovery broadcast

// Custom user-defined driver callback signatures
typedef float (*SwarmCustomSensorFn)();
typedef void (*SwarmCustomMultiSensorFn)(float* outValues, uint8_t& outCount);
typedef void (*SwarmCustomActuatorFn)(int16_t v1, int16_t v2, const char* data);

// ============================================================================
// ACTUATOR TYPES (Motors, Servos, Steppers, GPIO, Bus Protocols & Custom)
// ============================================================================
enum ActuatorType : uint8_t {
    ACT_NONE = 0,
    ACT_L298N,          // 6-pin Dual H-Bridge (ENA, IN1, IN2, ENB, IN3, IN4)
    ACT_DRV8833,        // 4-pin Dual H-Bridge (IN1, IN2, IN3, IN4)
    ACT_MOTOR_2PIN,     // Single 2-pin DC motor (IN1, IN2)
    ACT_SERVO,          // 50Hz Hobby Servo (pin, 0..180 degrees)
    ACT_STEPPER,        // Step/Dir/En Stepper Driver (A4988, DRV8825, TMC2209)
    ACT_DIGITAL_OUT,    // GPIO Output (LED, Relay, Electromagnet, Buzzer)
    ACT_PWM_OUT,        // Single PWM Output (0..255 duty)
    ACT_DAC_OUT,        // Analog DAC / PWM Output (0..255)
    ACT_UART_BUS,       // Hardware UART TX (transmits bytes/strings sent by Master)
    ACT_I2C_BUS,        // Hardware I2C Register Write (writes [reg=v1, val=v2] to i2c_addr)
    ACT_SPI_BUS,        // Hardware SPI Register Write (writes [reg=v1, val=v2] to CS pin)
    ACT_CUSTOM          // User-defined custom actuator callback
};

// ============================================================================
// SENSOR TYPES (Distance, Motion, Encoders, I2C, SPI, UART & Custom)
// ============================================================================
enum SensorType : uint8_t {
    SENS_NONE = 0,
    SENS_ULTRASONIC,    // HC-SR04 / JSN-SR04T (TRIG, ECHO) -> distance cm
    SENS_DIGITAL_IN,    // Bumper, Limit switch, IR obstacle, PIR, Line sensor, Hall
    SENS_ANALOG_IN,     // ADC (Battery voltage, LDR, Flex, Sharp IR, ACS712, Gas/Pot)
    SENS_TOUCH,         // Capacitive Touch pin
    SENS_ENCODER_QUAD,  // Hardware Interrupt Quadrature Wheel Encoder (pinA, pinB) -> ticks
    SENS_TACHOMETER,    // Single-pin Optical/Hall Speed Encoder (pin) -> pulse count
    SENS_DHT,           // DHT11 / DHT22 Temperature & Humidity (pin, model 11 or 22)
    SENS_MPU6050,       // I2C 6-Axis IMU (0x68 -> ax, ay, az, gx, gy, gz)
    SENS_LSM6DSOX,      // I2C 6-Axis IMU (0x6A -> onboard Nano RP2040 / Nano 33 IoT / LSM6DS)
    SENS_INA219,        // I2C Current/Voltage/Power Monitor (0x40 -> bus voltage V, current mA)
    SENS_VL53L0X,       // I2C Time-of-Flight Laser Rangefinder (0x29)
    SENS_GENERIC_I2C,   // Universal I2C Register Reader (any I2C address & register)
    SENS_SPI_DEVICE,    // Universal SPI Register Reader (CS, SCK, MISO, MOSI, reg, len)
    SENS_UART_BUS,      // Universal UART Stream Reader (parses numeric/byte stream)
    SENS_CUSTOM,        // User-defined 1-value custom sensor callback
    SENS_CUSTOM_MULTI,  // User-defined multi-value custom sensor callback
    SENS_WIFI_RSSI      // Onboard Wi-Fi Signal Strength (dBm)
};

struct ActuatorDescriptor {
    ActuatorType type = ACT_NONE;
    char name[16] = {0};
    uint8_t pins[6] = {0};       // GPIO / Bus pins (e.g. ENA..IN4 or CS, SCK, MISO, MOSI)
    uint8_t bus_addr = 0;        // I2C address or UART port number
    uint32_t bus_freq = 0;       // Baudrate (UART) or SPI clock Hz
    int16_t val1 = 0;            // Primary command (Left PWM / Angle / Reg / Steps / Digital)
    int16_t val2 = 0;            // Secondary command (Right PWM / Val / Step Speed)
    SwarmCustomActuatorFn custom_fn = nullptr;
};

struct SensorDescriptor {
    SensorType type = SENS_NONE;
    char name[16] = {0};
    uint8_t pins[6] = {0};       // GPIO / Bus pins (e.g. TRIG/ECHO, SDA/SCL, or CS/SCK/MISO/MOSI)
    uint8_t i2c_addr = 0;        // I2C address or UART port number
    uint8_t i2c_reg = 0;         // Register address to read (I2C or SPI)
    uint8_t i2c_len = 2;         // Number of bytes to read (I2C or SPI)
    uint8_t sub_index = 0;       // Encoder slot or DHT model (11/22)
    uint32_t bus_freq = 0;       // UART baudrate or SPI clock Hz
    bool pullup = false;
    float values[6] = {0.0f};    // Supports single-value AND multi-axis (up to 6 values)
    uint8_t value_count = 1;
    SwarmCustomSensorFn custom_fn = nullptr;
    SwarmCustomMultiSensorFn custom_multi_fn = nullptr;
};

#endif // SWARM_TYPES_H
