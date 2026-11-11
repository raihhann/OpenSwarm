#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string>
#include <cstring>
#include <cstdio>
#include <algorithm>
#define OUTPUT 1
#define INPUT 0
#define INPUT_PULLUP 2
#define HIGH 1
#define LOW 0
#define constrain(x,a,b) ((x)<(a)?(a):((x)>(b)?(b):(x)))
extern uint32_t fake_now;
extern std::string fake_incoming, fake_outgoing;
extern uint16_t fake_sender_port;
extern int fake_pins[256];
inline uint32_t millis() { return fake_now; }
inline void delay(uint32_t ms) { fake_now += ms; }
inline void pinMode(uint8_t, uint8_t) {}
inline void digitalWrite(uint8_t pin, int value) { fake_pins[pin] = value; }
inline void analogWrite(uint8_t pin, int value) { fake_pins[pin] = value; }
struct FakeSerial {
    void begin(int) {}
    template<class T> void print(const T&) {}
    template<class T> void println(const T&) {}
    void println() {}
};
static FakeSerial Serial;
struct IPAddress {
    bool operator!=(const IPAddress&) const { return false; }
};
struct WiFiUDP {
    void begin(uint16_t) {}
    int parsePacket() { return (int)fake_incoming.size(); }
    int read(char* out, size_t capacity) {
        size_t n = std::min(capacity, fake_incoming.size());
        memcpy(out, fake_incoming.data(), n);
        fake_incoming.clear(); return (int)n;
    }
    IPAddress remoteIP() { return IPAddress(); }
    uint16_t remotePort() { return fake_sender_port; }
    void beginPacket(IPAddress, uint16_t) { fake_outgoing.clear(); }
    void write(const uint8_t* data, size_t size) { fake_outgoing.append((const char*)data, size); }
    void endPacket() {}
};
