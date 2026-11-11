# Hardware registration reference

[Back to OpenSwarm](../README.md) · [Protocol](protocol.md)

These are declaration and host API entry points. Check the board pinout and HAL
capabilities before wiring; API presence does not establish a completed hardware
validation matrix. Linux and MCU drivers do not all implement identical features.


OpenSwarm supports both dedicated 1-line robotics drivers and **universal bus passthroughs (`SPI`, `I2C`, `UART`, and Custom Callbacks)** for extending hardware support. Availability depends on the HAL, backend, board and device protocol; a generic bus registration does not supply device-specific initialization or calibration:

### Actuators
| API Method | Hardware / Protocol | Master Python Call |
| :--- | :--- | :--- |
| `registerL298N(name, ena, in1, in2, enb, in3, in4)` | 6-pin Dual H-Bridge DC Motor Driver | `bot.drive(name, left, right)` |
| `registerDRV8833(name, in1, in2, in3, in4)` | 4-pin Dual H-Bridge DC Motor Driver | `bot.drive(name, left, right)` |
| `registerMotor2Pin(name, pinA, pinB)` | Single Reversible DC Motor | `bot.drive(name, speed)` |
| `registerServo(name, pin)` | 50 Hz Hobby Servo (`0°–180°`) | `bot.servo(name, angle)` |
| `registerStepper(name, stepPin, dirPin, enPin)` | Stepper Driver (`A4988`, `DRV8825`, `TMC2209`) | `bot.stepper(name, steps, delay_us)` |
| `registerDigitalOutput(name, pin)` / `registerPin()` | GPIO Output (LED, Relay, Solenoid, Buzzer) | `bot.digital_write(name, 1)` |
| `registerPWMOutput(name, pin)` | Variable PWM Output (`0–255`) | `bot.pwm_write(name, duty)` |
| `registerDACOutput(name, pin)` | True Analog DAC Output (`GPIO25`/`26`) | `bot.set_actuator(name, val)` |
| `registerI2CActuator(name, i2cAddr, sda, scl)` | Generic I2C Register Writer (`PCA9685`, `MCP23017`) | `bot.write_reg(name, reg, val)` |
| `registerSPIActuator(name, cs, sck, miso, mosi, hz)` | Generic SPI Register Writer | `bot.write_reg(name, reg, val)` |
| `registerUARTActuator(name, rx, tx, baud, uartNum)` | Generic Hardware UART Transmitter (`RS485`, Serial) | `bot.send_bus(name, data="...")` |
| `registerCustomActuator(name, callback)` | Custom User C++ Callback (`loop()` stays empty!) | `bot.send_bus(name, data, v1, v2)` |

### Sensors & Transceivers
| API Method | Hardware / Protocol | Streamed Telemetry (`bot.read(name)`) |
| :--- | :--- | :--- |
| `registerUltrasonic(name, trig, echo)` | `HC-SR04` / `JSN-SR04T` Ultrasonic | Distance in `cm` (`float`) |
| `registerVL53L0X(name, i2cAddr, sda, scl)` | `VL53L0X` I2C Laser ToF Rangefinder | Distance in `mm` (`float`) |
| `registerQuadratureEncoder(name, pinA, pinB)` | Hardware Interrupt Wheel Encoder | Cumulative ticks (`float`) |
| `registerTachometer(name, pin)` | Optical / Hall Speed Sensor | Pulse count (`float`) |
| `registerMPU6050(name, i2cAddr, sda, scl)` | 6-Axis I2C IMU (`MPU6050` Accel + Gyro) | `[ax, ay, az, gx, gy, gz]` (`g`, `deg/s`) |
| `registerLSM6DSOX(name, i2cAddr, sda, scl)` / `registerOnboardIMU(name)` | 6-Axis I2C IMU (Onboard Nano RP2040 Connect / `LSM6DS`) | `[ax, ay, az, gx, gy, gz]` (`g`, `deg/s`) |
| `registerINA219(name, i2cAddr, sda, scl)` | I2C Bus Voltage & Current Monitor | `[voltage_V, current_mA]` |
| `registerDHT(name, pin, model)` | `DHT11` / `DHT22` Temp & Humidity | `[temp_C, humidity_%]` |
| `registerBumper(name, pin, pullup)` | Contact Limit Switch / Microswitch | `1.0` (pressed) or `0.0` |
| `registerIRSensor(name, pin)` / `registerDigitalInput()` | IR Obstacle, Line, PIR, Hall Sensor | `1.0` or `0.0` |
| `registerAnalogInput(name, pin)` / `registerBatteryVoltage()` | 12-bit ADC (Battery, FSR, LDR, Pot) | Board-dependent raw ADC counts |
| `registerTouchPin(name, touchPin)` | Capacitive Touch Pin | Touch reading |
| `registerGenericI2C(name, addr, reg, len, sda, scl)` | **Any I2C Sensor** (`BME280`, `BH1750`, etc.) | Register value (`1–4` bytes) |
| `registerSPISensor(name, cs, reg, len, sck, miso, mosi)` | **Any SPI Sensor** (`MAX6675`, `AS5048A`, etc.) | Register value (`1–4` bytes) |
| `registerUARTSensor(name, rx, tx, baud, uartNum)` | **Any UART Sensor / Transceiver** (`LiDAR`, `GPS`, `RS485`) | Parsed float stream |
| `registerCustomSensor(name, callback)` | **Any 3rd-Party Arduino Library** | 20 Hz callback value(s) |
| `registerWiFiRSSI(name)` | Onboard Wi-Fi Signal Strength | Signal in `dBm` |
