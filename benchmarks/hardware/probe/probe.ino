// Test fixture only: use an unloaded GPIO/LED, not a robot actuator.
// Select the correct board and explicitly choose a free output-capable GPIO.
#include <Arduino.h>
#include <string.h>
#include <SwarmNode.h>  // Keep this as the last library include.

#define PROBE_PIN -1  // EDIT: a free GPIO number for your exact board, not a header pin number.
#if PROBE_PIN < 0
#error "Set PROBE_PIN to a free GPIO verified against your board pinout"
#endif

SwarmNode node("probe_esp32"); // EDIT: probe_rp2040 on the second board.
volatile int16_t value = 0;
volatile uint32_t acts = 0, stops = 0, hold_ms = 0, on_ms = 0, exec_ms = 0;

void applyProbe(int16_t v1, int16_t, const char* data) {
    uint32_t now = millis();
    if (strcmp(data, "STOP") == 0) {
        if (value != 0) hold_ms = now - on_ms;
        value = 0;
        ++stops;
    } else {
        value = v1;
        on_ms = now;
        exec_ms = now & 0x7FFF;
        ++acts;
    }
    digitalWrite(PROBE_PIN, value != 0 ? HIGH : LOW);
}

void setup() {
    pinMode(PROBE_PIN, OUTPUT);
    digitalWrite(PROBE_PIN, LOW);
    if (!node.connectWiFi("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD")) return;
    node.registerCustomActuator("probe", applyProbe);
    node.registerCustomSensor("value", []() -> float { return value; });
    node.registerCustomSensor("acts", []() -> float { return acts; });
    node.registerCustomSensor("stops", []() -> float { return stops; });
    node.registerCustomSensor("hold_ms", []() -> float { return hold_ms; });
    node.registerCustomSensor("exec_ms", []() -> float { return exec_ms; });
    node.start();
}
void loop() {}
