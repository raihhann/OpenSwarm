/*
 * SwarmNode — Universal Bus Protocols (SPI, I2C, UART) & Custom Driver Example
 *
 * Shows how a user can connect ANY sensor, actuator, or external transceiver over:
 *  1. Generic UART Bus (UART LiDAR, GPS, RS485, or UART LoRa transceivers like E32/RYLR998)
 *  2. Generic I2C Bus (Any I2C sensor register or I2C actuator/port-expander like PCA9685)
 *  3. Generic SPI Bus (Thermocouples, Magnetic Encoders, SPI DACs, or SPI transceivers)
 *  4. Custom User Callbacks (Bring any 3rd-party C++ library while keeping loop() 100% EMPTY!)
 */

#include <SwarmNode.h> // Or: #include <OpenSwarm.h>

SwarmNode node("esp32_custom_node");

void setup() {
    node.connectWiFi("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD");

    // ------------------------------------------------------------------------
    // 1. Generic UART Sensor & Actuator (e.g. UART LiDAR, GPS, RS485, UART LoRa)
    // ------------------------------------------------------------------------
    // Streams incoming serial values on RX=16, TX=17 to the Linux Master:
    node.registerUARTSensor("uart_rx", 16, 17, 9600, 2);
    // Transmits any string/bytes sent by the Linux Master (`bot.send_bus("uart_tx", data="...")`):
    node.registerUARTActuator("uart_tx", 16, 17, 9600, 2);

    // ------------------------------------------------------------------------
    // 2. Generic I2C Sensor & Actuator (Works with ANY I2C device or transceiver)
    // ------------------------------------------------------------------------
    // Read 2 bytes from register 0xFA on I2C address 0x76 (SDA=21, SCL=22) at 20Hz:
    node.registerGenericI2C("i2c_sensor", 0x76, 0xFA, 2, 21, 22);
    // Write [reg, val] commands from Linux Master (`bot.write_reg("i2c_chip", reg, val)`):
    node.registerI2CActuator("i2c_chip", 0x40, 21, 22);

    // ------------------------------------------------------------------------
    // 3. Generic SPI Sensor & Actuator
    // ------------------------------------------------------------------------
    // Read 2 bytes from register 0x00 on SPI device with CS=5 (SCK=18, MISO=19, MOSI=23):
    // node.registerSPISensor("spi_sensor", 5, 0x00, 2, 18, 19, 23);
    // Write [reg, val] commands from Linux Master to SPI device on CS=5:
    // node.registerSPIActuator("spi_act", 5, 18, 19, 23);

    // ------------------------------------------------------------------------
    // 4. Custom User Callbacks (For ANY custom protocol / 3rd-party library)
    // ------------------------------------------------------------------------
    // Runs automatically at 20Hz in the background daemon:
    node.registerCustomSensor("custom_sensor", []() -> float {
        return (float)millis() * 0.001f; // Replace with any custom hardware read!
    });

    // Runs automatically whenever the Linux Master sends a command to "custom_act":
    node.registerCustomActuator("custom_act", [](int16_t v1, int16_t v2, const char* data) {
        Serial.printf("[CustomActuator] Master sent v1=%d, v2=%d, data='%s'\n", v1, v2, data);
    });

    node.start();
}

void loop() {
    // Still 100% EMPTY!
}
