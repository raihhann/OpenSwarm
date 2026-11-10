# SwarmNode — Zero-Control-Logic Arduino Slave Library (`OpenSwarm`)

**SwarmNode** is the microcontroller Slave library for the [**OpenSwarm**](https://github.com/raihhann/OpenSwarm) Distributed Robotics Framework.

### Core Rule
* **Slaves ONLY declare Wi-Fi, Node ID, and attached sensor/actuator pins inside `setup()`.**
* **`void loop()` is 100% empty.**
* **100% of robot control logic runs remotely on the Linux Master (`openswarm-master`).**

### Supported Boards (`v0.4.1` — Wi-Fi boards only)
* **ESP32 Family (`hal_esp32.h`):** `ESP32`, `ESP32-S2`, `ESP32-S3`, `ESP32-C3` (FreeRTOS task on Core 0)
* **RP2040 Family (`hal_rp2040.h`):** `Arduino Nano RP2040 Connect` (`WiFiNINA` + Mbed RTOS thread + onboard `LSM6DSOX` 6-axis IMU) & `Raspberry Pi Pico W` (`WiFi.h`, daemon on Core 0 alongside the Wi-Fi driver)
* **Arduino UNO (`hal_uno.h`):** `Arduino UNO R4 WiFi` (`WiFiS3`), `Arduino UNO WiFi Rev2` (`WiFiNINA` + onboard `LSM6DS3` IMU)
* **Arduino Nano (`hal_nano.h`):** `Arduino Nano 33 IoT` (`WiFiNINA` + onboard `LSM6DS3` IMU)

> Boards without native Wi-Fi (UNO R3, UNO R4 Minima, Classic Nano, Nano Every) are not supported.

> **Tip (UNO R4 WiFi / UNO WiFi Rev2 / Nano 33 IoT / Pico W):** on these boards SwarmNode keeps your `loop()` empty by renaming it with a macro. Put `#include <SwarmNode.h>` **last** in your sketch so other libraries' `loop()` methods are not affected.

---

## 1. Installation in Arduino IDE

1. Open **Tools -> Manage Libraries...** (or click the Library Manager icon).
2. Search for **`SwarmNode`**, select the library by Mohammed Raihan Soniwala, and click **Install**. Choose the latest version when prompted.
3. Include the library in your sketch with either:
   ```cpp
   #include <SwarmNode.h>
   // OR
   #include <OpenSwarm.h>
   ```

You can also install it manually from the [**`SwarmNode` branch**](https://github.com/raihhann/OpenSwarm/tree/SwarmNode): download the branch ZIP, then choose **Sketch -> Include Library -> Add .ZIP Library...**.

---

## 2. Quick Start (`ESP32_LED_Test.ino`)

```cpp
#include <SwarmNode.h>

SwarmNode node("esp32_node");

void setup() {
    node.connectWiFi("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD");

    // Declare Pin 2 (Built-in LED) and Wi-Fi RSSI sensor — Zero Control Logic!
    node.registerDigitalOutput("led", 2);
    node.registerWiFiRSSI("rssi");

    node.start();
}

void loop() {
    // 100% EMPTY! Controlled remotely from the Linux Master.
}
```

---

## 3. Complete API Reference

### Actuators
* `node.registerL298N(name, ena, in1, in2, enb, in3, in4)` — 6-pin Dual H-Bridge (`-255..255`)
* `node.registerDRV8833(name, in1, in2, in3, in4)` — 4-pin Dual H-Bridge (`-255..255`)
* `node.registerMotor2Pin(name, pinA, pinB)` — Single 2-pin DC motor (`-255..255`)
* `node.registerServo(name, pin)` — 50 Hz Hobby Servo (`0..180°`)
* `node.registerStepper(name, stepPin, dirPin, enPin)` — Step/Dir Stepper (`A4988`, `DRV8825`, `TMC2209`)
* `node.registerDigitalOutput(name, pin)` / `node.registerPin(name, pin, OUTPUT)` — GPIO Output
* `node.registerPWMOutput(name, pin)` — Variable PWM Output (`0..255`)
* `node.registerDACOutput(name, pin)` — True Analog DAC Output (`GPIO25`/`26`)

### Sensors
* `node.registerUltrasonic(name, trigPin, echoPin)` — `HC-SR04` Ultrasonic distance (`cm`)
* `node.registerVL53L0X(name, i2cAddr, sdaPin, sclPin)` — I2C Laser ToF rangefinder
* `node.registerQuadratureEncoder(name, pinA, pinB)` — Hardware interrupt quadrature wheel encoder
* `node.registerTachometer(name, pin)` — Optical/Hall pulse counter
* `node.registerMPU6050(name, i2cAddr, sdaPin, sclPin)` — 6-DOF I2C IMU (`[ax, ay, az, gx, gy, gz]`)
* `node.registerLSM6DSOX(name, i2cAddr, sdaPin, sclPin)` / `node.registerOnboardIMU(name)` — 6-DOF I2C IMU (Onboard Arduino Nano RP2040 Connect `0x6A`)
* `node.registerINA219(name, i2cAddr, sdaPin, sclPin)` — I2C Voltage & Current (`[V, mA]`)
* `node.registerDHT(name, pin, model)` — `DHT11` / `DHT22` (`[temp_C, hum_%]`)
* `node.registerBumper(name, pin, pullup)` — Contact limit switch
* `node.registerIRSensor(name, pin, pullup)` — IR obstacle / line sensor
* `node.registerDigitalInput(name, pin, pullup)` — Generic digital input
* `node.registerAnalogInput(name, pin)` / `node.registerBatteryVoltage(name, adcPin)` — ADC input
* `node.registerTouchPin(name, touchPin)` — Capacitive touch sensor
* `node.registerWiFiRSSI(name)` — Wi-Fi signal strength (`dBm`)

### Universal Bus Protocols & Custom Drivers (`SPI`, `I2C`, `UART`, Callbacks)
* `node.registerSPISensor(...)` & `node.registerSPIActuator(...)` — Raw SPI register read/write
* `node.registerGenericI2C(...)` & `node.registerI2CActuator(...)` — Raw I2C register read/write
* `node.registerUARTSensor(...)` & `node.registerUARTActuator(...)` — Raw UART serial stream RX/TX
* `node.registerCustomSensor(name, fn)` & `node.registerCustomActuator(name, fn)` — Custom C++ callbacks
