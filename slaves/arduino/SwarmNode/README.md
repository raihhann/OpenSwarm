# SwarmNode — Zero-Touch Hardware Declaration Slave Library

**SwarmNode** turns microcontrollers (`ESP32`, `Arduino UNO`, `Arduino Nano`, `RP2040`) into network-transparent Slave nodes for distributed multi-robot systems.

### Core Rule
* **Slaves ONLY declare Wi-Fi/Network, Node ID, and attached sensor/actuator pins inside `setup()`.**
* **`void loop()` is 100% empty.**
* **100% of robot control logic runs remotely on the Linux Master.**

---

## 1. Quick Start (ESP32 Slave)

```cpp
#include <SwarmNode.h>

SwarmNode node("tug_esp32");

void setup() {
    node.connectWiFi("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD");

    // Declare attached hardware pins ONLY — zero control logic!
    node.registerL298N("drive", 14, 27, 26, 32, 25, 33);
    node.registerUltrasonic("front_sonar", 5, 18);
    node.registerBumper("front_bumper", 4);
    node.registerWiFiRSSI("rssi");

    node.start();
}

void loop() {
    // Intentionally 100% empty!
}
```

---

## 2. Supported ESP32 Actuators & Sensors

### Actuators
| Method | Description |
| :--- | :--- |
| `registerL298N(name, ena, in1, in2, enb, in3, in4)` | 6-pin Dual H-Bridge DC Motor Driver (`-255..255` left/right) |
| `registerDRV8833(name, in1, in2, in3, in4)` | 4-pin Dual H-Bridge DC Motor Driver (`-255..255` left/right) |
| `registerMotor2Pin(name, pinA, pinB)` | Single 2-pin Reversible DC Motor (`-255..255`) |
| `registerServo(name, pin)` | Standard 50Hz Hobby Servo (`0..180` degrees) |
| `registerStepper(name, stepPin, dirPin, enPin)` | Step/Dir Stepper Driver (`A4988`, `DRV8825`, `TMC2209`) |
| `registerDigitalOutput(name, pin)` | GPIO Output (LED, Relay, Electromagnet, Buzzer) |
| `registerPWMOutput(name, pin)` | Single PWM Output (`0..255` duty) |
| `registerDACOutput(name, pin)` | ESP32 True Analog DAC Output (`GPIO25` / `GPIO26`) |

### Sensors
| Method | Description |
| :--- | :--- |
| `registerUltrasonic(name, trigPin, echoPin)` | `HC-SR04` / `JSN-SR04T` Ultrasonic Distance (`cm`) |
| `registerVL53L0X(name, i2cAddr, sdaPin, sclPin)` | I2C Time-of-Flight Laser Rangefinder |
| `registerQuadratureEncoder(name, pinA, pinB)` | Hardware Interrupt Quadrature Wheel Encoder (`ticks`) |
| `registerTachometer(name, pin)` | Single-pin Optical/Hall Speed Sensor (`pulses`) |
| `registerMPU6050(name, i2cAddr, sdaPin, sclPin)` | 6-Axis I2C IMU (`[ax, ay, az, gx, gy, gz]`) |
| `registerINA219(name, i2cAddr, sdaPin, sclPin)` | I2C Bus Voltage & Current Monitor (`[V, mA]`) |
| `registerGenericI2C(name, i2cAddr, reg, bytes, sda, scl)` | Universal I2C Register Reader (works with any I2C sensor) |
| `registerBumper(name, pin, pullup)` | Contact Switch / Microswitch |
| `registerIRSensor(name, pin, pullup)` | IR Obstacle / Line Tracking Sensor |
| `registerDigitalInput(name, pin, pullup)` | Generic Digital Input (Limit, PIR, Hall, Tilt) |
| `registerAnalogInput(name, pin)` | Analog ADC Input (FSR Force, Flex, LDR, Potentiometer, Gas) |
| `registerBatteryVoltage(name, adcPin)` | Battery Voltage Divider ADC |
| `registerTouchPin(name, touchPin)` | ESP32 Capacitive Touch Sensor |
| `registerDHT(name, pin, model)` | `DHT11` / `DHT22` Temperature & Humidity (`[temp_C, hum_%]`) |
| `registerWiFiRSSI(name)` | Onboard Wi-Fi Signal Strength (`dBm`) |

---

## 3. Installing in Arduino IDE & Uploading to GitHub

### Option A: Local Development Symlink / Copy (Fastest)
Copy or symlink the `SwarmNode` folder into your Arduino libraries directory:
```powershell
Copy-Item -Path "d:\Projects\ConnectedSystems\SwarmNode" -Destination "$HOME\Documents\Arduino\libraries\SwarmNode" -Recurse -Force
```

### Option B: Install as `.ZIP` Library in Arduino IDE
1. Compress the `SwarmNode` folder into `SwarmNode.zip`.
2. In Arduino IDE, click **Sketch -> Include Library -> Add .ZIP Library...** and select `SwarmNode.zip`.

### Option C: Upload to GitHub as an Official Arduino Library
1. Push the repository to GitHub (`https://github.com/raihhann/OpenSwarm`) and switch to the `arduino-library` branch.
2. Create a GitHub Release tagged `v0.1.0` — GitHub will automatically generate a `.zip` package that anyone can install directly in Arduino IDE or PlatformIO!
