#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <new>
#include "SwarmNode.h"
#include "SwarmProtocol.h"

static unsigned long new_calls = 0;
void* operator new(std::size_t size) {
    ++new_calls;
    void* ptr = std::malloc(size);
    if (!ptr) throw std::bad_alloc();
    return ptr;
}
void operator delete(void* ptr) noexcept { std::free(ptr); }
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete[](void* ptr) noexcept { ::operator delete(ptr); }

int main(int argc, char** argv) {
    const int iterations = argc > 1 ? std::atoi(argv[1]) : 100000;
    // Host-only corpus, prepared outside the timed region; it is not part of
    // SwarmNode or the embedded memory budget. Vary fields to prevent measuring
    // only a constant packet whose parsing could be hoisted by the optimizer.
    static char corpus[32767][160];
    for (int i = 0; i < 32767; ++i) {
        std::snprintf(corpus[i], sizeof(corpus[i]),
            "{\"cmd\":\"ACT\",\"name\":\"servo\",\"angle\":%d,\"seq\":%d,\"at_ms\":%d,\"lease_ms\":250}",
            i % 181, i + 1, (18450 + i) & 0x7FFF);
    }
    volatile unsigned long checksum = 0;
    int16_t previous = 0;
    unsigned long accepted = 0;
    const unsigned long before = new_calls;
    auto start = std::chrono::steady_clock::now();
    for (int i = 0; i < iterations; ++i) {
        const char* packet = corpus[i % 32767];
        char cmd[16], name[16];
        int16_t angle, seq, at_ms, lease;
        bool valid = SwarmProtocol::extractString(packet, "cmd", cmd, sizeof(cmd))
            && SwarmProtocol::extractString(packet, "name", name, sizeof(name))
            && SwarmProtocol::extractInt(packet, "angle", angle)
            && SwarmProtocol::extractInt(packet, "seq", seq)
            && SwarmProtocol::extractInt(packet, "at_ms", at_ms)
            && SwarmProtocol::extractInt(packet, "lease_ms", lease);
        if (!valid) return 2;
        // Vary sequence state so both wraparound and the acceptance path run.
        bool ok = SwarmProtocol::acceptSeq(seq, previous);
        accepted += ok ? 1 : 0;
        checksum += (unsigned long)(angle + seq + lease + name[0] + cmd[0]
            + SwarmProtocol::scheduleDelayMs(at_ms, 18400) + (ok ? 1 : 0));
    }
    double elapsed = std::chrono::duration<double, std::micro>(
        std::chrono::steady_clock::now() - start).count();
    std::printf("{\"actuators\":%d,\"sensors\":%d,\"pointer_bytes\":%zu,"
        "\"actuator_descriptor_bytes\":%zu,\"sensor_descriptor_bytes\":%zu,"
        "\"actuator_table_bytes\":%zu,\"sensor_table_bytes\":%zu,"
        "\"sizeof_swarmnode_host_stubbed_bytes\":%zu,\"iterations\":%d,"
        "\"elapsed_us\":%.6f,\"us_per_cmd\":%.6f,\"commands_per_second\":%.3f,"
        "\"new_calls_in_loop\":%lu,\"accepted\":%lu,\"checksum\":%lu}\n",
        SWARM_MAX_ACTUATORS, SWARM_MAX_SENSORS, sizeof(void*),
        sizeof(ActuatorDescriptor), sizeof(SensorDescriptor),
        sizeof(ActuatorDescriptor) * SWARM_MAX_ACTUATORS,
        sizeof(SensorDescriptor) * SWARM_MAX_SENSORS, sizeof(SwarmNode), iterations,
        elapsed, elapsed / iterations, iterations * 1e6 / elapsed,
        new_calls - before, accepted, (unsigned long)checksum);
}
