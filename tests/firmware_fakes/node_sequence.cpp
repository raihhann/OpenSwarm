// Compile and drive the real SwarmNode.cpp; only hardware/transport are fake.
#include "SwarmNode.h"
#include <cassert>
#include <vector>
uint32_t fake_now = 100;
std::string fake_incoming, fake_outgoing;
uint16_t fake_sender_port = 40000;
int fake_pins[256] = {};
std::vector<int> applied;
int stops = 0;
void _swarmUserLoop() {}
void callback(int16_t a, int16_t, const char* data) {
    if (strcmp(data, "STOP") == 0) ++stops;
    else applied.push_back(a);
}
void send(SwarmNode& node, const char* json) {
    fake_incoming = json; node._backgroundTick();
}
void ack(SwarmNode& node, int seq) {
    send(node, "{\"cmd\":\"PING\"}");
    assert(fake_outgoing.find("\"ack\":" + std::to_string(seq)) != std::string::npos);
}
int main() {
    SwarmNode node("regression");
    assert(node.registerCustomActuator("drive", callback));
    node.start();
    send(node, R"({"cmd":"ACT","name":"drive","value":100,"seq":10})");
    send(node, R"({"cmd":"ACT","name":"drive","value":110,"seq":11})");
    send(node, R"({"cmd":"PING","seq":9})");
    ack(node, 11);
    send(node, R"({"cmd":"ACT","name":"drive","value":100,"seq":10})");
    assert(applied.size() == 2 && applied.back() == 110);
    send(node, R"({"cmd":"PIN","pin":2,"value":1,"seq":10})");
    assert(fake_pins[2] == 0);
    ack(node, 11);
    assert(fake_outgoing.find("\"seq_drop\":2") != std::string::npos);
    send(node, R"({"cmd":"STOP","seq":8})");
    assert(stops == 1); ack(node, 11);
    // Scheduled command survives stale data and delayed PING.
    send(node, R"({"cmd":"ACT","name":"drive","value":120,"seq":12,"at_ms":150})");
    send(node, R"({"cmd":"PING","seq":9})");
    send(node, R"({"cmd":"ACT","name":"drive","value":100,"seq":10})");
    assert(applied.size() == 2);
    fake_now = 150; node._backgroundTick();
    assert(applied.size() == 3 && applied.back() == 120);
    send(node, R"({"cmd":"ACT","name":"drive","value":130,"seq":13,"at_ms":200})");
    send(node, R"({"cmd":"STOP","seq":8})");
    fake_now = 200; node._backgroundTick();
    assert(applied.size() == 3 && stops == 2); ack(node, 13);
    // A changed endpoint establishes a new session; PING alone does not.
    ++fake_sender_port;
    send(node, R"({"cmd":"ACT","name":"drive","value":1,"seq":32766})");
    send(node, R"({"cmd":"PING","seq":32767})");
    send(node, R"({"cmd":"ACT","name":"drive","value":2,"seq":1})");
    send(node, R"({"cmd":"PING","seq":32766})");
    send(node, R"({"cmd":"ACT","name":"drive","value":99,"seq":32767})");
    assert(applied.back() == 2); ack(node, 1);
    send(node, R"({"cmd":"ACT","name":"drive","value":3,"seq":2})");
    assert(applied.back() == 3); ack(node, 2);
    // Actual watchdog tick establishes the other supported session boundary.
    fake_now += 501; node._backgroundTick();
    send(node, R"({"cmd":"ACT","name":"drive","value":4,"seq":1})");
    assert(applied.back() == 4); ack(node, 1);
}
