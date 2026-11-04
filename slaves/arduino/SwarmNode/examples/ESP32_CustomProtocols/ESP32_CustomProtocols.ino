/*
 * SwarmNode — Universal Bus Protocols (LoRa, SPI, I2C, UART) & Custom Driver Example
 *
 * Shows how a user can connect ANY sensor or actuator over:
 *  1. LoRa (both SPI SX1276/SX1278/RFM95 AND UART E32/RYLR998 LoRa modules)
 *  2. Raw SPI Bus (Thermocouples, Magnetic Encoders, SPI DACs)
 *  3. Raw I2C Bus (Any I2C sensor or I2C port expander/driver)
 *  4. Raw UART Bus (GPS, UART LiDAR, RS485, Barcode scanners)
 *  5. Custom User Callbacks (Bring any 3rd-party library while keeping loop() 100% EMPTY!)
 */

#include <SwarmNode.h> // Or: #include <OpenSwarm.h>

SwarmNode node("esp32_custom_node");

void setup() {
    node.connectWiFi("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD");

    // ------------------------------------------------------------------------
    // 1. LoRa Support (SPI SX1276/SX1278 OR UART LoRa E32/RYLR998)
    // ------------------------------------------------------------------------
    // Option A: SPI LoRa (CS=5, RST=14, IRQ=2, 868MHz, SCK=18, MISO=19, MOSI=23)
    node.registerLoRaSPI("lora_radio", 5, 14, 2, 868000000UL, 18, 19, 23);

    // Option B: UART LoRa (RX=16, TX=17, Baud=9600, M0=4, M1=15, UART2)
    // node.registerLoRaUART("lora_uart", 16, 17, 9600, 4, 15, 2);

    // ------------------------------------------------------------------------
    // 2. Generic SPI Sensor & Actuator
    // ------------------------------------------------------------------------
    // Read 2 bytes from register 0x00 on SPI device with CS=15
    // node.registerSPISensor("spi_temp", 15, 0x00, 2);
    // Write [reg, val] commands from Linux Master to SPI device on CS=15
    // node.registerSPIActuator("spi_dac", 15);

    // ------------------------------------------------------------------------
    // 3. Generic I2C Sensor & Actuator
    // ------------------------------------------------------------------------
    // Read 2 bytes from register 0xFA on I2C device 0x76 (SDA=21, SCL=22)
    // node.registerGenericI2C("bme_raw", 0x76, 0xFA, 2, 21, 22);
    // Write [reg, val] commands from Linux Master to I2C chip 0x40 (e.g. PCA9685)
    // node.registerI2CActuator("i2c_pwm_chip", 0x40, 21, 22);

    // ------------------------------------------------------------------------
    // 4. Generic UART Sensor & Actuator (e.g. UART LiDAR, GPS, RS485)
    // ------------------------------------------------------------------------
    // node.registerUARTSensor("uart_lidar", 16, 17, 115200, 2);
    // node.registerUARTActuator("rs485_tx", 16, 17, 115200, 2);

    // ------------------------------------------------------------------------
    // 5. Custom User Callbacks (For ANY custom protocol / 3rd-party library)
    // ------------------------------------------------------------------------
    // Runs automatically at 20Hz in the background FreeRTOS task:
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
