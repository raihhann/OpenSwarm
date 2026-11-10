"""Compile the actual allocation-free firmware parser on the host compiler."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import ROOT


@unittest.skipUnless(shutil.which("g++"), "Host g++ compiler is not installed")
class FirmwareProtocolTests(unittest.TestCase):
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
