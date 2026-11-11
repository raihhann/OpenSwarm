"""Compile the actual allocation-free firmware parser on the host compiler."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import ROOT


@unittest.skipUnless(shutil.which("g++"), "Host g++ compiler is not installed")
class FirmwareProtocolTests(unittest.TestCase):
    def test_actual_runtime_control_reordering(self):
        from benchmarks.memory import _work_directory
        fixtures = ROOT / "tests/firmware_fakes"
        with _work_directory() as directory:
            for profile in ([], ["-D__AVR__"]):
                with self.subTest(profile=profile):
                    executable = directory / "node_sequence.exe"
                    result = subprocess.run([
                        "g++", "-std=c++11", "-Wall", "-Wextra", *profile,
                        "-DARDUINO_SAMD_NANO_33_IOT", "-DHAL_NANO_H",
                        "-I", str(fixtures), "-I", str(ROOT / "slaves/arduino/SwarmNode/src"),
                        "-include", str(fixtures / "fake_hal.h"),
                        str(ROOT / "slaves/arduino/SwarmNode/src/SwarmNode.cpp"),
                        str(fixtures / "node_sequence.cpp"), "-o", str(executable)],
                        capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_flat_command_contract(self):
        source = r'''
#include "SwarmProtocol.h"
#include <assert.h>
int main() {
    using namespace SwarmProtocol;
    char text[64]; int16_t value = 123;
    assert(extractString("{\"cmd\":\"ACT\",\"data\":\"hello \\\"robot\\\"\\n\"}", "data", text, sizeof(text)));
    assert(strcmp(text, "hello \"robot\"\n") == 0);
    assert(extractInt("{\"value\":-32768}", "value", value) && value == -32768);
    assert(extractInt("{\"value\":32767}", "value", value) && value == 32767);
    assert(!extractInt("{\"value\":40000}", "value", value));
    assert(!extractInt("{\"value\":\"oops\"}", "value", value));
    assert(!extractInt("{\"value\":true}", "value", value));
    assert(!extractInt("{\"value\":1.5}", "value", value));
    assert(!extractInt("{\"value\":01}", "value", value));
    assert(!extractInt("{\"value\":1,\"value\":2}", "value", value));
    assert(!extractString("{\"cmd\":\"PING\"}junk", "cmd", text, sizeof(text)));
    assert(!extractString("{\"cmd\":\"PING\",}", "cmd", text, sizeof(text)));
    assert(!extractString("{\"cmd\":\"PING\"", "cmd", text, sizeof(text)));
    assert(!extractString("{\"cmd\":\"PING\"}", "cmd", text, 3));
    assert(extractString("{\"data\":\"cmd: STOP\",\"cmd\":\"PING\"}", "cmd", text, sizeof(text)));
    assert(strcmp(text, "PING") == 0);
    assert(validName("shoulder_servo"));
    assert(!validName("name\"bad"));
    assert(!validName("longer_than_fifteen"));

    int16_t lastSeq = 0;
    assert(!acceptSeq(0, lastSeq));
    assert(acceptSeq(5, lastSeq) && lastSeq == 5);
    assert(!acceptSeq(5, lastSeq) && lastSeq == 5);
    assert(!acceptSeq(4, lastSeq) && lastSeq == 5);
    assert(acceptSeq(6, lastSeq) && lastSeq == 6);
    // Delayed control packets may still be serviced, but cannot rewind ack.
    assert(!acceptSeq(1, lastSeq) && lastSeq == 6);
    assert(!acceptSeq(5, lastSeq) && lastSeq == 6);
    // A session boundary is explicit; there is no control-packet reset flag.
    lastSeq = 0;
    assert(acceptSeq(1, lastSeq) && lastSeq == 1);
    // Wraparound from 32767 -> 1 is accepted
    lastSeq = 32767;
    assert(acceptSeq(1, lastSeq) && lastSeq == 1);

    // Old pre-wrap traffic is rejected after wrapping, in either direction.
    assert(!acceptSeq(32767, lastSeq) && lastSeq == 1);
    assert(acceptSeq(2, lastSeq) && lastSeq == 2);
    assert(!acceptSeq(32760, lastSeq) && lastSeq == 2);
    lastSeq = 100;
    assert(acceptSeq(16483, lastSeq) && lastSeq == 16483);
    lastSeq = 100;
    assert(!acceptSeq(16484, lastSeq) && lastSeq == 100);

    // Original delayed-PING counterexample: seq 10, 11, 9, 10.
    lastSeq = 0;
    assert(acceptSeq(10, lastSeq));
    assert(acceptSeq(11, lastSeq));
    assert(!acceptSeq(9, lastSeq));
    assert(!acceptSeq(10, lastSeq));
    assert(lastSeq == 11);

    // 15-bit modular scheduleDelayMs tests (including wraparound 32767 -> 0)
    assert(scheduleDelayMs(1050, 1000) == 50);
    assert(scheduleDelayMs(990, 1000) == -10);
    assert(scheduleDelayMs(20, 32758) == 30);   // 32758 + 30 = 32788 -> & 0x7FFF = 20
    assert(scheduleDelayMs(32758, 20) == -30);
    assert(scheduleDelayMs(32767, 0) == -1);
    assert(scheduleDelayMs(0, 32767) == 1);
    assert(scheduleDelayMs(16383, 0) == 16383);
    assert(scheduleDelayMs(16384, 0) == -16384);

    // lease_ms extraction bounds check
    assert(extractInt("{\"cmd\":\"ACT\",\"name\":\"drive\",\"left\":120,\"lease_ms\":250}", "lease_ms", value) && value == 250);
    assert(!extractInt("{\"cmd\":\"ACT\",\"name\":\"drive\",\"lease_ms\":40000}", "lease_ms", value));
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "protocol.cpp").write_text(source)
            executable = path / "protocol.exe"
            subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "slaves/arduino/SwarmNode/src"), str(path / "protocol.cpp"),
                "-o", str(executable)], check=True, capture_output=True, timeout=30)
            subprocess.run([str(executable)], check=True, capture_output=True, timeout=10)
