#!/usr/bin/env python3
"""Seeded, offline preliminary validation of OpenSwarm's implemented protocol.

Run: python benchmarks/run_benchmarks.py
Logical workloads are deterministic; measured host timings necessarily vary.
"""

import argparse
import hashlib
import json
import math
import os
import platform
import random
import socket
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "master", ROOT / "slaves/linux"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from benchmarks.memory import run_memory
from benchmarks.simulation import Simulation, Clock, MemorySocket
from openswarm_slave.hal_linux import LinuxHAL
from openswarm_slave.node import SwarmNode

SEED = 2027


def statistics(values):
    ordered = sorted(values)
    def percentile(fraction):
        if not ordered:
            return None
        rank = fraction * (len(ordered) - 1)
        low, high = math.floor(rank), math.ceil(rank)
        return round(ordered[low] + (ordered[high] - ordered[low]) * (rank - low), 6)
    return {"count": len(ordered), "mean": round(sum(ordered) / len(ordered), 6) if ordered else None,
            "p50": percentile(.5), "p95": percentile(.95), "p99": percentile(.99),
            "max": ordered[-1] if ordered else None}


def run_benchmark_2_hydra_sync_under_jitter(poses=200, lead_ms=30.0,
                                         jitter_levels_ms=(5., 15., 25., 40.)):
    roles = [("arm_base_esp32", 12450., ("servo",)),
             ("arm_elbow_rp2040", 85320., ("servo",)),
             ("arm_shoulder_gripper_rpi", 410900., ("shoulder_servo", "gripper_servo"))]
    rows = []
    for scheduler, periods in [("idealized_1ms", (1., 1., 1.)),
                               ("heterogeneous_polling", (2., 2., 10.))]:
        for spread in jitter_levels_ms:
            mode_results = {}
            for scheduled in (False, True):
                rng = random.Random(SEED + int(spread * 100))
                with Simulation() as sim:
                    for index, (name, offset, names) in enumerate(roles):
                        sim.add_node(name, offset, 4300 + index, periods[index], names)
                    sim.calibrate()
                    errors = [abs(sim.master.get(e["node"].node_id).clock_offset_ms - e["offset_ms"])
                              for e in sim.slaves.values()]
                    skews, late_commands, late_poses = [], 0, 0
                    start = sim.clock.us
                    for pose in range(poses):
                        sim.until(start + pose * 50000)
                        late = False
                        for e in sim.slaves.values():
                            e["forward_us"] = 3000 + round(rng.uniform(0, spread) * 1000)
                            if e["forward_us"] > lead_ms * 1000:
                                late_commands += len(e["node"]._actuators)
                                late = True
                        late_poses += int(late)
                        commands = [(name, act, 30 + pose % 120) for name, _, names in roles for act in names]
                        before = len(sim.execution)
                        if scheduled:
                            count = sim.master.sync_actuate(commands, lead_ms=lead_ms)
                            if count != 4:
                                raise AssertionError("Not all HydraArm joints were dispatched")
                        else:
                            for name, actuator, angle in commands:
                                sim.master.get(name).set_actuator(actuator, angle)
                        if pose % 4 == 0:
                            # Real SDK keepalive cadence; the new estimator does
                            # not use ACT ACKs as a substitute for clock probes.
                            for name, _, _ in roles:
                                sim.master.get(name).ping()
                        sim.until(start + (pose + 1) * 50000)
                        errors.extend(abs(sim.master.get(e["node"].node_id).clock_offset_ms - e["offset_ms"])
                                      for e in sim.slaves.values())
                        executed = sim.execution[before:]
                        if len(executed) != 4:
                            raise AssertionError("A pose did not execute exactly four joint commands")
                        times = [event["time_us"] / 1000 for event in executed]
                        skews.append(round(max(times) - min(times), 6))
                    mode_results["scheduled" if scheduled else "baseline"] = {
                        "skew_ms": statistics(skews), "raw_skew_ms": skews,
                        "late_commands": late_commands if scheduled else None,
                        "late_pose_count": late_poses if scheduled else None,
                        "clock_offset_error_ms": statistics(errors)}
            rows.append({"scheduler": scheduler, "poll_period_ms": list(periods),
                         "jitter_spread_ms": spread, "one_way_delay_support_ms": [3., 3. + spread],
                         "within_lead_horizon": 3. + spread <= lead_ms, **mode_results})
    return {"kind": "seeded discrete-event simulation using real SwarmMaster and Linux SwarmNode methods",
            "poses_per_case": poses, "lead_ms": lead_ms, "jitter_distribution": "Uniform(0, spread) + 3 ms base delay",
            "roles": [{"node": name, "initial_uptime_ms": offset, "actuators": list(names)} for name, offset, names in roles],
            "calibration": "Three PING/STATE exchanges with symmetric 3 ms one-way delay, then 5 Hz PING under the trial's injected delay; no assigned clock estimates. Clock errors include initial and per-pose observations.",
            "scope": "MCU names are roles, not physical processor emulators. Execution records software callbacks, not shaft movement. Poll periods are declared simulation assumptions; no OS/network sleeps or instruction timing.",
            "results": rows}


def run_benchmark_3_swarm_scaling(node_counts=(1, 5, 10, 20, 50), ticks_per_scale=40):
    rows = []
    for count in node_counts:
        with Simulation() as sim:
            for index in range(count):
                sim.add_node("node_%02d" % index, 5000. + index * 1370., 4400 + index)
            sim.calibrate()
            sim.command_counts = {"ACT": 0, "PING": 0, "STOP": 0}
            sim.state_count = 0
            sim.rx_latency_ms.clear()
            sim.rtt_samples_ms.clear()
            sim.master_cpu_ns = 0
            batches = []
            cpu_tx_ns = 0
            start = sim.clock.us
            wall_start = time.perf_counter()
            for tick in range(ticks_per_scale):
                sim.until(start + tick * 50000)
                before = time.perf_counter_ns()
                cpu = time.process_time_ns()
                for endpoint in sim.slaves.values():
                    remote = sim.master.get(endpoint["node"].node_id)
                    remote.servo("servo", tick % 180)
                    if tick % 4 == 0:
                        remote.ping()  # Equivalent 5 Hz keepalive traffic; no real thread scheduling.
                cpu_tx_ns += time.process_time_ns() - cpu
                batches.append((time.perf_counter_ns() - before) / 1e6)
                # Scheduled 20 Hz telemetry, in addition to immediate PING replies.
                for endpoint in sim.slaves.values():
                    sim.event(start + tick * 50000 + 5000, endpoint["node"]._send_telemetry)
                sim.until(start + (tick + 1) * 50000)
            host_elapsed = time.perf_counter() - wall_start
            duration = ticks_per_scale * .05
            errors = [abs(sim.master.get(e["node"].node_id).clock_offset_ms - e["offset_ms"])
                      for e in sim.slaves.values()]
            tx_count = sum(sim.command_counts.values())
            cpu_seconds = (cpu_tx_ns + sim.master_cpu_ns) / 1e9
            rows.append({"nodes": count, "simulated_duration_s": duration,
                "command_packets": dict(sim.command_counts), "telemetry_packets": sim.state_count,
                "total_packets": tx_count + sim.state_count,
                "delivered_packets_per_simulated_second": (tx_count + sim.state_count) / duration,
                "primary_act_state_rate_pps": 40 * count,
                "rx_processing_latency_ms": statistics(sim.rx_latency_ms),
                "tx_batch_latency_ms": statistics(batches), "rtt_ms": statistics(sim.rtt_samples_ms),
                "clock_offset_error_ms": statistics(errors),
                "master_measured_cpu_s": cpu_seconds,
                "projected_one_core_cpu_pct_at_workload_rate": 100 * cpu_seconds / duration,
                "host_harness_wall_s": host_elapsed,
                "in_process_service_rate_pps": (tx_count + sim.state_count) / host_elapsed})
    return {"kind": "host microbenchmark with a discrete-event network",
            "ticks_per_scale": ticks_per_scale, "act_hz": 20, "periodic_state_hz": 20, "ping_hz": 5,
            "scope": "Actual SDK dispatch/serialization and receive/drain/state-update paths; no OS UDP, sockets, threads, congestion or physical Wi-Fi. RX latency is host processing time, not network latency. CPU includes measurement-call overhead; service rate includes harness work and is not maximum wire capacity.",
            "results": rows}


def _sequence_trial(packets):
    with patch("time.monotonic", return_value=100.):
        node = SwarmNode("sequence", hal=LinuxHAL(verbose_sim=False, backend="sim"))
        applied = []
        node.register_custom_actuator("servo", lambda v1, v2, data: applied.append(v1))
        node._sock = MemorySocket()
        for packet in packets:
            node._sock.incoming.append((json.dumps(packet).encode(), ("127.0.0.1", 40000)))
            node._handle_incoming()
    return {"applied_commands": len(applied),
            "backward_inversions": sum(b < a for a, b in zip(applied, applied[1:])),
            "seq_drop": node._dropped_out_of_order, "last_angle": applied[-1]}


def _deadlock_trial(lease_ms=None, heartbeats=True):
    clock = Clock()
    start = clock.us
    with patch("time.monotonic", clock.monotonic):
        node = SwarmNode("lease", hal=LinuxHAL(verbose_sim=False, backend="sim"))
        changes = []
        node.register_custom_actuator("drive", lambda v1, v2, data: changes.append((clock.us - start, v1)))
        class PollSocket(MemorySocket):
            def recvfrom(self, count):
                if self.incoming and self.incoming[0][0] <= clock.us:
                    _, packet = self.incoming.popleft()
                    return packet, ("127.0.0.1", 40000)
                if clock.us >= start + 2_501_000:
                    node._running = False
                else:
                    clock.us += 1000
                raise socket.timeout()
        channel = PollSocket()
        node._sock = channel
        initial = {"cmd": "ACT", "name": "drive", "left": 200, "seq": 1}
        if lease_ms is not None:
            initial["lease_ms"] = lease_ms
        channel.incoming.append((start, json.dumps(initial).encode()))
        if heartbeats:
            for index in range(1, 13):
                channel.incoming.append((start + index * 200000,
                    json.dumps({"cmd": "PING", "seq": index + 1}).encode()))
        # Suppress only discovery, which otherwise probes the host's network interface.
        node._send_hello = lambda: None
        node._running = True
        node._background_loop()  # Exercise actual watchdog AND scheduling/lease polling.
        stopped = next((us / 1000 for us, value in changes if value == 0), None)
        return {"lease_ms": lease_ms, "heartbeat_hz": 5 if heartbeats else 0,
                "observation_ms": 2501, "poll_ms": 1, "time_to_stop_ms": stopped,
                "right_censored": stopped is None, "still_energized_at_end": changes[-1][1] != 0,
                "lease_exp": node._lease_expirations, "wd_trips": node._watchdog_trips}


def run_benchmark_4_safety_interlocks():
    rng = random.Random(SEED)
    originals = [{"cmd": "ACT", "name": "servo", "angle": round(index * 180 / 199), "seq": index + 1}
                 for index in range(200)]
    inject_after = set(rng.sample(range(6, 200), 30))
    stream = []
    for index, packet in enumerate(originals):
        stream.append(packet)
        if index in inject_after:
            stream.append(dict(originals[index - rng.randint(2, 5)]))
    baseline = _sequence_trial([{k: v for k, v in p.items() if k != "seq"} for p in stream])
    protected = _sequence_trial(stream)
    # This once-failing control/data ordering is a benchmark acceptance gate.
    reordered_control = _sequence_trial([
        {"cmd": "ACT", "name": "servo", "angle": 100, "seq": 10},
        {"cmd": "ACT", "name": "servo", "angle": 110, "seq": 11},
        {"cmd": "PING", "seq": 9},
        {"cmd": "ACT", "name": "servo", "angle": 100, "seq": 10},
    ])
    if (reordered_control["backward_inversions"] != 0 or
            reordered_control["seq_drop"] != 1 or reordered_control["last_angle"] != 110):
        raise RuntimeError("Delayed PING reopened stale ACT acceptance")
    loss_indices = set(random.Random(SEED + 1).sample(range(200), 30))
    loss = _sequence_trial([packet for index, packet in enumerate(originals) if index not in loss_indices])
    protected["stale_rejection_pct"] = protected["seq_drop"] / 30 * 100
    return {"kind": "deterministic fault injection into the real Linux node implementation",
        "sequence": {"primary_commands": 200, "angle_range": [0, 180], "stale_injected": 30,
            "injection_pct_of_primary": 15., "stale_fraction_of_delivered_pct": 30 / len(stream) * 100,
            "delivered_packets": len(stream), "baseline": baseline, "protected": protected,
            "reordered_control_probe": reordered_control,
            "packet_loss_trial": {"lost_commands": 30, "loss_pct": 15., **loss}},
        "deadlock": {"transport_only": _deadlock_trial(), "lease_150ms": _deadlock_trial(150),
                     "total_transport_loss": _deadlock_trial(heartbeats=False)},
        "scope": "Reordering trial re-inserts older packets after newer packets; 15% is relative to primary commands, not all delivered packets. Deadlock stops application sends while keepalives continue. No-lease stop time is right-censored, not proof of infinite energization. Logical callback stops do not establish physical stopping time or emergency-stop coverage on every driver."}


def source_hashes():
    files = [ROOT / "master/openswarm" / name for name in ("__init__.py", "master.py", "node.py", "protocol.py", "virtual_slave.py")]
    files += [ROOT / "projects/hydra_arm/master/virtual_arm_slaves.py"]
    files += [ROOT / "slaves/linux/openswarm_slave" / name for name in ("node.py", "protocol.py")]
    files += [ROOT / "slaves/arduino/SwarmNode/src" / name for name in ("SwarmNode.h", "SwarmNode.cpp", "SwarmTypes.h", "SwarmProtocol.h")]
    files += sorted((ROOT / "benchmarks").glob("*.py")) + [ROOT / "benchmarks/memory_probe.cpp"]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def run_all_benchmarks(parser_iterations=100000, write_outputs=True, output_dir=None):
    from openswarm import __version__ as master_version
    start = time.perf_counter()
    result = {"schema_version": 1, "seed": SEED,
        "methodology": "Seeded software-only validation; deterministic inputs/logical outcomes, variable measured host timings. No physical hardware or network I/O.",
        "environment": {"python": sys.version.split()[0], "platform": platform.platform(),
            "openswarm_master_version": master_version,
            "machine": platform.machine(), "processor": platform.processor(), "logical_cpus": os.cpu_count(),
            "perf_counter_resolution_s": time.get_clock_info("perf_counter").resolution},
        "source_sha256": source_hashes(),
        "benchmark_1_memory_and_parser": run_memory(parser_iterations),
        "benchmark_2_hydra_sync_under_jitter": run_benchmark_2_hydra_sync_under_jitter(),
        "benchmark_3_swarm_scaling": run_benchmark_3_swarm_scaling(),
        "benchmark_4_safety_interlocks": run_benchmark_4_safety_interlocks()}
    logical = {"seed": SEED, "sync": result["benchmark_2_hydra_sync_under_jitter"],
               "safety": result["benchmark_4_safety_interlocks"],
               "scale_counts": [{k: row[k] for k in ("nodes", "total_packets", "clock_offset_error_ms")}
                                for row in result["benchmark_3_swarm_scaling"]["results"]]}
    result["logical_results_sha256"] = hashlib.sha256(json.dumps(logical, sort_keys=True).encode()).hexdigest()
    result["total_runtime_sec"] = time.perf_counter() - start
    result["runtime_target_sec"] = 10
    result["within_runtime_target"] = result["total_runtime_sec"] < 10
    if write_outputs:
        from benchmarks.report import generate_report_markdown
        directory = Path(output_dir) if output_dir else ROOT / "benchmarks"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (directory / "REPORT.md").write_text(generate_report_markdown(result), encoding="utf-8")
        result["total_runtime_sec"] = time.perf_counter() - start
        result["within_runtime_target"] = result["total_runtime_sec"] < 10
        (directory / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (directory / "REPORT.md").write_text(generate_report_markdown(result), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "benchmarks")
    args = parser.parse_args()
    result = run_all_benchmarks(output_dir=args.output_dir)
    print("Benchmark suite: %.3f s; logical fingerprint %s" % (result["total_runtime_sec"], result["logical_results_sha256"][:12]))
    print("Outputs: %s" % args.output_dir)
    print("Software simulation and host measurements; consult REPORT.md before citing figures.")


if __name__ == "__main__":
    main()
