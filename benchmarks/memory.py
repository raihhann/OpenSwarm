"""Host measurements and explicitly labeled target-layout projections."""

import json
import os
import re
import shutil
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ROOT / "slaves/arduino/SwarmNode/src"
PROFILES = {"avr_8bit": (6, 8), "mcu_32bit": (14, 18)}
BUFFERS = {"rx": 160, "hello_tx": 256, "state_tx": 384}


@contextmanager
def _work_directory():
    # Some MSYS Python builds create mode-0700 temporary directories with an
    # unusable Windows ACL. These build inputs contain no private data.
    base = (ROOT / "benchmarks/build").resolve()
    base.mkdir(exist_ok=True)
    directory = base / ("probe-" + uuid.uuid4().hex)
    directory.mkdir(mode=0o777)
    try:
        yield directory
    finally:
        if base not in directory.resolve().parents:
            raise RuntimeError("Build directory escaped benchmark workspace")
        shutil.rmtree(directory)


def _fields(body):
    body = re.sub(r"//[^\n]*", "", body)
    return re.findall(r"^\s*(\w+)\s+(\w+)(?:\[(\w+)\])?\s*(?:=[^;]*)?;", body, re.M)


def _projection(profile):
    """Model common AVR/ILP32 ABIs; verify descriptor sizes if cross tools exist."""
    avr = profile == "avr_8bit"
    capacities = dict(zip(("SWARM_MAX_ACTUATORS", "SWARM_MAX_SENSORS"), PROFILES[profile]))
    pointer = 2 if avr else 4
    types = {"char": (1, 1), "uint8_t": (1, 1), "bool": (1, 1), "uint16_t": (2, 1 if avr else 2),
             "int16_t": (2, 1 if avr else 2), "uint32_t": (4, 1 if avr else 4),
             "float": (4, 1 if avr else 4), "ActuatorType": (1, 1), "SensorType": (1, 1)}
    for name in ("SwarmCustomActuatorFn", "SwarmCustomSensorFn", "SwarmCustomMultiSensorFn"):
        types[name] = (pointer, 1 if avr else 4)
    source = (INCLUDE / "SwarmTypes.h").read_text()
    for name in ("ActuatorDescriptor", "SensorDescriptor"):
        body = source.split("struct " + name + " {", 1)[1].split("\n};", 1)[0]
        offset, alignment = 0, 1
        for field_type, _, count in _fields(body):
            size, align = types[field_type]
            offset = (offset + align - 1) // align * align
            offset += size * (int(count) if count else 1)
            alignment = max(alignment, align)
        types[name] = ((offset + alignment - 1) // alignment * alignment, alignment)
    node = (INCLUDE / "SwarmNode.h").read_text().split("private:", 1)[1]
    known, omitted = 0, []
    for field_type, name, count in _fields(node):
        if field_type not in types:
            omitted.append(name)
            continue
        number = capacities[count] if count in capacities else (int(count) if count else 1)
        known += types[field_type][0] * number
    acts, sensors = PROFILES[profile]
    return {"basis": "ABI model (not a complete target build)",
            "actuator_descriptor_bytes": types["ActuatorDescriptor"][0],
            "sensor_descriptor_bytes": types["SensorDescriptor"][0],
            "actuator_table_bytes": types["ActuatorDescriptor"][0] * acts,
            "sensor_table_bytes": types["SensorDescriptor"][0] * sensors,
            "known_member_payload_bytes": known, "omitted_members": omitted,
            "known_members_plus_buffer_budget_bytes": known + sum(BUFFERS.values()),
            "target_sizeof_swarmnode_bytes": None,
            "assumptions": "AVR: 2-byte function pointers/alignment 1; ILP32: 4-byte pointers/alignment up to 4; float=4, bool=1. Inter-member class padding and transport/IP objects excluded."}


def _cross_descriptor_sizes(profile, directory):
    stem = "avr" if profile == "avr_8bit" else "arm-none-eabi"
    compiler = shutil.which(stem + "-g++")
    if not compiler:
        package = "toolchain-atmelavr" if stem == "avr" else "toolchain-gccarmnoneeabi"
        candidate = Path.home() / ".platformio/packages" / package / "bin" / (stem + "-g++.exe")
        compiler = str(candidate) if candidate.exists() else None
    if not compiler:
        return {"status": "unavailable"}
    nm = Path(compiler).with_name(stem + "-nm" + Path(compiler).suffix)
    source = directory / "cross.cpp"
    source.write_text('#include "SwarmTypes.h"\nextern "C" { char actuator_size[sizeof(ActuatorDescriptor)]; char sensor_size[sizeof(SensorDescriptor)]; }\n')
    flags = ["-mmcu=atmega4809"] if stem == "avr" else ["-mcpu=cortex-m0plus", "-mthumb"]
    try:
        obj = directory / (stem + ".o")
        subprocess.run([compiler, "-std=c++11", *flags, "-I", str(directory), "-I", str(INCLUDE),
                        "-c", str(source), "-o", str(obj)], check=True, capture_output=True, timeout=2.5)
        output = subprocess.run([str(nm), "-S", "--radix=d", str(obj)], check=True,
                                capture_output=True, text=True, timeout=1).stdout
        sizes = {name: int(re.search(r"\d+\s+(\d+)\s+\w\s+" + name + r"\b", output).group(1))
                 for name in ("actuator_size", "sensor_size")}
        return {"status": "measured_from_target_object", "compiler": compiler,
                "flags": flags, "actuator_descriptor_bytes": sizes["actuator_size"],
                "sensor_descriptor_bytes": sizes["sensor_size"]}
    except (subprocess.SubprocessError, OSError, AttributeError) as exc:
        stderr = getattr(exc, "stderr", b"") or b""
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        return {"status": "unavailable", "reason": type(exc).__name__ + ": " + str(exc)[-180:], "stderr": stderr[-1000:]}


def run_memory(iterations=100000):
    compiler = shutil.which(os.environ.get("CXX", "g++"))
    result = {"iterations": iterations, "compiler": compiler, "profiles": {}, "boards": [],
              "packet_buffer_bytes": BUFFERS, "packet_buffer_sum_bytes": sum(BUFFERS.values()),
              "buffer_note": "Automatic function-local arrays, not static class members. Their sum is a component budget, not a measured simultaneous stack high-water mark.",
              "micro_ros_reference": {"bytes": 24576, "basis": "User-requested illustrative 24 KiB reference; NOT a measured or universal micro-ROS minimum.",
                  "source": "https://micro.vulcanexus.org/docs/concepts/benchmarking/memo_prof/"}}
    if compiler:
        try:
            result["compiler_version"] = subprocess.run([compiler, "--version"], capture_output=True,
                text=True, timeout=1, check=True).stdout.splitlines()[0]
        except (OSError, subprocess.SubprocessError):
            result["compiler_version"] = "unavailable"
    with _work_directory() as directory:
        (directory / "Arduino.h").write_text('#pragma once\n#include <stdint.h>\n#include <stddef.h>\n#define OUTPUT 1\nstruct WiFiUDP { unsigned char placeholder; };\nstruct IPAddress { unsigned char bytes[4]; };\n')
        for profile in PROFILES:
            row = {"target_projection": _projection(profile), "host_status": "unavailable"}
            if compiler:
                executable = directory / (profile + ".exe")
                flags = ["-std=c++11", "-O2", "-DESP32", "-DHAL_ESP32_H"]
                if profile == "avr_8bit":
                    flags.append("-D__AVR__")
                try:
                    subprocess.run([compiler, *flags, "-I", str(directory), "-I", str(INCLUDE),
                                    str(Path(__file__).with_name("memory_probe.cpp")), "-o", str(executable)],
                                   check=True, capture_output=True, timeout=2.5)
                    output = subprocess.run([str(executable), str(iterations)], check=True,
                                            capture_output=True, text=True, timeout=2).stdout
                    row.update(host_status="measured", host=json.loads(output), flags=flags)
                except (subprocess.SubprocessError, OSError, ValueError) as exc:
                    row["reason"] = str(exc)[:200]
            else:
                row["reason"] = "g++ not found; no timing or sizeof results are invented."
            row["cross_compiler"] = _cross_descriptor_sizes(profile, directory)
            cross = row["cross_compiler"]
            if cross["status"] == "measured_from_target_object":
                for field in ("actuator_descriptor_bytes", "sensor_descriptor_bytes"):
                    if cross[field] != row["target_projection"][field]:
                        raise RuntimeError("Target ABI disagrees with projection: " + field)
            result["profiles"][profile] = row
    for board, sram, profile in [("UNO WiFi Rev2", 6144, "avr_8bit"),
                                 ("Nano 33 IoT", 32768, "mcu_32bit"),
                                 ("UNO R4 WiFi", 32768, "mcu_32bit"),
                                 ("RP2040", 270336, "mcu_32bit"),
                                 ("ESP32 (classic)", 532480, "mcu_32bit")]:
        projection = result["profiles"][profile]["target_projection"]
        partial = projection["known_members_plus_buffer_budget_bytes"]
        result["boards"].append({"board": board, "sram_bytes": sram, "profile": profile,
            "known_component_budget_bytes": partial, "partial_sram_pct": round(partial / sram * 100, 3),
            "full_target_static_bytes": None, "micro_ros_reference_pct": round(24576 / sram * 100, 3)})
    return result
