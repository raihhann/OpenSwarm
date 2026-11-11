"""Live SDK trial; estimates clock-mapped callback skew, NOT independently measured physical skew."""
import argparse
import json
import platform
import time
from pathlib import Path

from openswarm import SwarmMaster
from openswarm import __version__ as master_version


class ExecutionObservationTimeout(TimeoutError):
    def __init__(self, mode, pose, nodes, counts, snapshots):
        super().__init__("Missing execution telemetry; no missing pose may be silently discarded")
        self.diagnostics = dict(mode=mode, pose=pose, nodes=[
            dict(node=n.node_id, expected_acts=count + 1, observed=snapshot)
            for n, count, snapshot in zip(nodes, counts, snapshots)])


def trial(targets, poses=200, lead_ms=30, seed=2027, record_callback=None):
    import random
    rng = random.Random(seed)
    modes = ["immediate", "scheduled"]
    rng.shuffle(modes)
    records = []
    with SwarmMaster() as master:
        nodes = []
        for name, address in targets:
            ip, separator, port = address.partition(":")
            nodes.append(master.connect(name, ip=ip, port=int(port) if separator else 4210, timeout=3))
        time.sleep(2)  # Actual PING/STATE clock-estimation warmup.
        if any(not hasattr(n, "snapshot") for n in nodes):
            raise RuntimeError("Install the prepared openswarm-master 0.2.1 patch for coherent clock snapshots")
        calibration = [n.snapshot()["clock"] for n in nodes]
        calibrated_at = time.monotonic()
        if any(c is None or not c["fresh"] for c in calibration):
            raise RuntimeError("No usable clock estimate on every board")
        for mode in modes:
            for index in range(poses):
                counts = [n.snapshot()["sensors"].get("acts") for n in nodes]
                if any(c is None for c in counts):
                    raise RuntimeError("The probe fixture is not running on every board")
                dispatch_at = time.monotonic()
                if mode == "scheduled":
                    master.sync_actuate([(n, "probe", index + 1) for n in nodes], lead_ms=lead_ms)
                else:
                    for n in nodes:
                        n.set_actuator("probe", v1=index + 1)
                deadline = time.monotonic() + 1
                while True:
                    snapshots = [n.snapshot() for n in nodes]
                    if all(s["sensors"].get("acts", 0) >= c + 1 for s, c in zip(snapshots, counts)):
                        break
                    if time.monotonic() > deadline:
                        raise ExecutionObservationTimeout(mode, index, nodes, counts, snapshots)
                    time.sleep(0.002)
                callbacks, raw, intervals = [], [], []
                for n, count, snapshot, clock in zip(nodes, counts, snapshots, calibration):
                    sensors = snapshot["sensors"]
                    if sensors["acts"] != count + 1 or sensors["value"] != index + 1:
                        raise RuntimeError("Unexpected competing command/session or missing probe event")
                    uptime = snapshot["uptime_ms"]
                    delta = ((int(sensors["exec_ms"]) - (uptime & 0x7FFF) + 16384) & 0x7FFF) - 16384
                    estimate = uptime + delta - clock["offset_ms"]
                    drift = max(0, time.monotonic() - calibrated_at) * clock["drift_ppm_assumption"] / 1000.0
                    bounds = [uptime + delta - clock["upper_ms"] - drift,
                              uptime + delta + 1 - clock["lower_ms"] + drift]
                    intervals.append(bounds)
                    callbacks.append(estimate)
                    raw.append(dict(node=n.node_id, sensors=sensors, uptime_ms=uptime,
                                    clock_offset_snapshot_ms=clock["offset_ms"], calibration=clock,
                                    execution_master_interval_ms=bounds,
                                    causal_interval_violation=bounds[1] < dispatch_at * 1000,
                                    live_snapshot=snapshot, rtt_ms=snapshot["rtt_ms"], jitter_ms=snapshot["jitter_ms"]))
                records.append(dict(mode=mode, pose=index, host_dispatch_mono_s=dispatch_at,
                                    estimated_skew_ms=max(callbacks) - min(callbacks), nodes=raw,
                                    conditional_skew_interval_ms=[max(0, max(v[0] for v in intervals) - min(v[1] for v in intervals)),
                                                                  max(v[1] for v in intervals) - min(v[0] for v in intervals)]))
                if record_callback is not None:
                    record_callback(records[-1])
                time.sleep(max(0, 0.1 - (time.monotonic() - dispatch_at)))
    summaries = {}
    for mode in modes:
        values = sorted(r["estimated_skew_ms"] for r in records if r["mode"] == mode)
        def percentile(q):
            position = (len(values) - 1) * q
            low = int(position)
            return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (position - low)
        summaries[mode] = dict(count=len(values), mean=sum(values) / len(values),
                               p50=percentile(.5), p95=percentile(.95), p99=percentile(.99), maximum=max(values))
    violations = sum(n["causal_interval_violation"] for r in records for n in r["nodes"])
    return dict(schema_version=2, host=platform.platform(), master_version=master_version,
                measurement_mapping="frozen pretrial PING calibration; command ACKs never recalibrate measurement",
                causal_interval_violations=violations, calibration_mono_s=calibrated_at,
                seed=seed, order=modes, poses_per_mode=poses, lead_ms=lead_ms,
                injected_jitter=False, estimated_skew_ms=summaries, records=records,
                limitations="Physical boards over live network; execution times mapped with the framework's own estimated offsets. No independent timing reference: offset bias, drift, quantization and telemetry consistency affect the estimate. Cannot prove physical synchronization accuracy.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", action="append", required=True, help="NODE_ID=IP[:PORT], repeat once per board")
    parser.add_argument("--poses", type=int, default=200)
    parser.add_argument("--lead-ms", type=float, default=30)
    parser.add_argument("--seed", type=int, default=2027)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.poses < 1 or len(args.node) < 2:
        parser.error("Use at least two nodes and one pose")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Preserve completed poses even if a later command/connection fails.
    with args.output.with_suffix(".jsonl").open("w", encoding="utf-8") as raw:
        def record(pose):
            raw.write(json.dumps(pose) + "\n")
            raw.flush()
        try:
            result = trial([value.split("=", 1) for value in args.node], args.poses, args.lead_ms, args.seed, record)
        except Exception as exc:
            result = dict(status="FAIL", error=str(exc), targets=args.node,
                          master_version=master_version, diagnostics=getattr(exc, "diagnostics", None),
                          seed=args.seed, poses_per_mode=args.poses, lead_ms=args.lead_ms,
                          partial_records=str(args.output.with_suffix(".jsonl")))
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result.get("estimated_skew_ms", result), indent=2))
    print("Saved", args.output)
    raise SystemExit(int(result.get("status") == "FAIL" or result.get("causal_interval_violations", 0) > 0))
