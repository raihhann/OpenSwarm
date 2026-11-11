#pragma once
#include "SwarmTypes.h"
namespace SwarmHAL {
inline const char* boardName() { return "HOST_FAKE"; }
inline std::string localIP() { return "127.0.0.1"; }
inline IPAddress broadcastIP() { return IPAddress(); }
inline bool connectNetwork(const char*, const char*, uint32_t) { return true; }
inline void setupActuator(ActuatorDescriptor&) {}
inline void setupSensor(SensorDescriptor&) {}
inline void readSensor(SensorDescriptor&) {}
inline void writeActuator(ActuatorDescriptor& act, int16_t a, int16_t b, const char* data) {
    act.val1 = a; act.val2 = b;
    if (act.custom_fn) act.custom_fn(a, b, data);
}
}
