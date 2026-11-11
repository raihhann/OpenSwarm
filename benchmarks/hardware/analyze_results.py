"""Audit saved live-board trials without modifying the raw evidence."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics


def stats(values):
    if not values:
        return {"n": 0}
    values = sorted(values)
    def percentile(q):
        position = (len(values) - 1) * q
        low = int(position)
        return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (position - low)
    return dict(n=len(values), minimum=min(values), mean=statistics.mean(values),
                p50=percentile(.5), p95=percentile(.95), p99=percentile(.99), maximum=max(values))


def mapped_execution(node):
    uptime = node["uptime_ms"]
    delta = ((int(node["sensors"]["exec_ms"]) - (uptime & 32767) + 16384) & 32767) - 16384
    return uptime + delta - node["clock_offset_snapshot_ms"]


def verify_case_evidence(data):
    """Check cumulative raw callback/counter evidence, separately from PASS flags."""
    packets = data["packet_log"]
    starts = [i for i, p in enumerate(packets) if p["direction"] == "tx" and p["packet"].get("cmd") == "ACT" and
              ((p["packet"].get("seq") == 10 and p["packet"].get("value") in (100, 120)) or
               p["packet"].get("seq") == 32766 or
               (p["packet"].get("seq") == 1 and p["packet"].get("value") == 100))]
    # Ignore the deliberately stale seq=10 ACT copies in the first case.
    unique_starts = []
    for index in starts:
        if unique_starts and packets[index]["packet"].get("seq") == 10 and "at_ms" not in packets[index]["packet"]:
            continue
        unique_starts.append(index)
    findings = []
    for case, start in zip(data["cases"], unique_starts):
        if case["status"] != "PASS":
            continue
        before = [p["packet"] for p in packets[:start] if p["direction"] == "rx" and p["packet"].get("type") == "STATE"]
        if not before:
            findings.append(case["name"] + ": missing initial STATE")
            continue
        base = before[-1]
        end = next((i for i in range(start + 1, len(packets)) if packets[i]["direction"] == "tx" and
                    packets[i]["packet"].get("cmd") == "STOP" and "seq" not in packets[i]["packet"]), len(packets))
        states = [p["packet"] for p in packets[start:end] if p["direction"] == "rx" and p["packet"].get("type") == "STATE"]
        name = case["name"]
        increment = 2 if name == "delayed_ping_and_stale_stop" else 3 if name == "sequence_wraparound" else 1
        if not states or max(p["sensors"]["acts"] for p in states) != base["sensors"]["acts"] + increment:
            findings.append(name + ": callback count inconsistent")
        drop_increment = 2 if name == "delayed_ping_and_stale_stop" else 1 if name in (
            "sequence_wraparound", "scheduled_preservation_and_stop_cancellation") else 0
        if not states or max(p.get("seq_drop", 0) for p in states) != base.get("seq_drop", 0) + drop_increment:
            findings.append(name + ": stale-drop count inconsistent")
        counter = "lease_exp" if name.startswith("lease_") else "wd_trips" if name.startswith("watchdog_") else None
        if counter and states[-1].get(counter, 0) != base.get(counter, 0) + 1:
            findings.append(name + ": stop counter inconsistent")
        if counter and states[-1]["sensors"]["value"] != 0:
            findings.append(name + ": final output nonzero")
        if name == "no_lease_with_5hz_ping":
            active = [p for p in states if p["sensors"]["acts"] == base["sensors"]["acts"] + 1]
            if not active or any(p["sensors"]["value"] != 100 for p in active):
                findings.append(name + ": observed active interval inconsistent")
    if len(unique_starts) != len(data["cases"]):
        findings.append("Could not identify every case boundary in packet log")
    return findings


def analyze(directory):
    files = sorted(path for board in ("esp32", "rp2040", "rpi") for path in directory.glob(board + "-run*.json"))
    result = dict(kind="audit of supplied hardware callback/telemetry evidence", boards={}, failures=[], sync={}, inputs={})
    for board in ("esp32", "rp2040", "rpi"):
        board_files = [p for p in files if p.name.startswith(board + "-")]
        statuses, by_case = Counter(), defaultdict(Counter)
        measures = defaultdict(list)
        provenance, raw_checks = [], {}
        for path in board_files:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw_checks[path.name] = verify_case_evidence(data)
            provenance.append(dict(file=path.name, revision=data.get("revision"),
                                   host=data.get("host"), worktree_status=data.get("worktree_status")))
            for case in data["cases"]:
                statuses[case["status"]] += 1
                by_case[case["name"]][case["status"]] += 1
                if case["status"] != "PASS":
                    failure = dict(file=path.name, case=case["name"], error=case.get("error"))
                    packets = data["packet_log"]
                    first = next((i for i, p in enumerate(packets) if p["direction"] == "tx" and "at_ms" in p["packet"]), None)
                    if first is not None and case["name"].startswith("scheduled_"):
                        next_case = next((i for i in range(first + 1, len(packets))
                                          if packets[i]["direction"] == "tx" and "lease_ms" in packets[i]["packet"]), len(packets))
                        segment = packets[first:next_case]
                        origin = packets[first]["host_mono_s"]
                        failure["tx_timeline_ms"] = [dict(ms=(p["host_mono_s"] - origin) * 1000,
                                                         packet=p["packet"]) for p in segment if p["direction"] == "tx"]
                        failure["rx_ack_values"] = list(dict.fromkeys(p["packet"].get("ack") for p in segment if p["direction"] == "rx"))
                        failure["watchdog_values"] = list(dict.fromkeys(p["packet"].get("wd_trips", 0) for p in segment if p["direction"] == "rx"))
                    result["failures"].append(failure)
                for key in ("onboard_hold_ms", "execution_lateness_ms"):
                    if key in case.get("detail", {}):
                        measures[case["name"]].append(case["detail"][key])
            times = [p["host_mono_s"] for p in data["packet_log"]]
            if any(b < a for a, b in zip(times, times[1:])):
                raise ValueError("Packet-log host timestamps go backward: " + path.name)
        result["boards"][board] = dict(files=len(board_files), statuses=dict(statuses),
            cases={k: dict(v) for k, v in by_case.items()}, timing_ms={k: stats(v) for k, v in measures.items()},
            raw_consistency_checks=raw_checks, provenance=provenance)
    for path in sorted(directory.glob("sync-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        sidecar = path.with_suffix(".jsonl")
        raw_lines = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines() if line.strip()] if sidecar.exists() else None
        sync = dict(status=data.get("status", "completed"), error=data.get("error"), modes={},
                    jsonl_identical_to_records=raw_lines == data.get("records"),
                    lead_ms=data.get("lead_ms"), seed=data.get("seed"), order=data.get("order"),
                    injected_jitter=data.get("injected_jitter"), stored_summary_mismatches=[])
        for mode in ("scheduled", "immediate"):
            rows = [r for r in data.get("records", []) if r["mode"] == mode]
            if not rows:
                continue
            skews, per_node = [], defaultdict(lambda: defaultdict(list))
            for row in rows:
                estimates = [mapped_execution(n) for n in row["nodes"]]
                skew = max(estimates) - min(estimates)
                if abs(skew - row["estimated_skew_ms"]) > 1e-6:
                    raise ValueError("Recorded skew disagrees with raw fields: " + path.name)
                skews.append(skew)
                for node, estimate in zip(row["nodes"], estimates):
                    arrays = per_node[node["node"]]
                    arrays["acts"].append(node["sensors"]["acts"])
                    arrays["values"].append(node["sensors"]["value"])
                    arrays["offset_ms"].append(node["clock_offset_snapshot_ms"])
                    arrays["rtt_ms"].append(node["rtt_ms"])
                    arrays["mapped_delay_ms"].append(estimate - row["host_dispatch_mono_s"] * 1000)
            measured = stats(skews)
            stored = data.get("estimated_skew_ms", {}).get(mode, {})
            for key in ("mean", "p50", "p95", "p99", "maximum"):
                if key not in stored or abs(stored[key] - measured[key]) > 1e-6:
                    sync["stored_summary_mismatches"].append(mode + "/" + key)
            node_summary = {}
            for name, arrays in per_node.items():
                node_summary[name] = dict(
                    act_first=arrays["acts"][0], act_last=arrays["acts"][-1],
                    nonunit_counter_steps=sum(b != a + 1 for a, b in zip(arrays["acts"], arrays["acts"][1:])),
                    incorrect_values=sum(value != row["pose"] + 1 for value, row in zip(arrays["values"], rows)),
                    offset_span_ms=max(arrays["offset_ms"]) - min(arrays["offset_ms"]),
                    rtt_ms=stats(arrays["rtt_ms"]), mapped_delay_ms=stats(arrays["mapped_delay_ms"]),
                    negative_mapped_delays=sum(v < 0 for v in arrays["mapped_delay_ms"]))
            span = rows[-1]["host_dispatch_mono_s"] - rows[0]["host_dispatch_mono_s"]
            sync["modes"][mode] = dict(estimated_skew_ms=measured, nodes=node_summary,
                unique_pose_indices=len({r["pose"] for r in rows}), dispatch_span_s=span,
                observed_interval_rate_hz=(len(rows) - 1) / span if span else None)
        if all(k in sync["modes"] for k in ("scheduled", "immediate")):
            sync["estimated_mean_reduction_pct"] = 100 * (1 - sync["modes"]["scheduled"]["estimated_skew_ms"]["mean"] /
                                                         sync["modes"]["immediate"]["estimated_skew_ms"]["mean"])
        result["sync"][path.name] = sync
        files.append(path)
        if sidecar.exists():
            files.append(sidecar)
    result["inputs"] = {p.name: dict(bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files}
    return result


def report(result):
    lines = ["# Hardware evidence review", "",
        "This review preserves the supplied raw files and includes every recorded failure. Measurements are probe callback/telemetry observations on user-reported physical boards, not independently measured GPIO edges or motor motion.", "",
        "## Trial inventory and functional outcomes", "",
        "| Board | Run files | Case PASS | Case FAIL | Scheduled test PASS / attempted |", "| --- | --- | --- | --- | --- |"]
    for name, board in result["boards"].items():
        scheduled = board["cases"].get("scheduled_preservation_and_stop_cancellation", {})
        lines.append(f"| {name} | {board['files']} | {board['statuses'].get('PASS', 0)} | {board['statuses'].get('FAIL', 0)} | {scheduled.get('PASS', 0)} / {sum(scheduled.values())} |")
    lines += ["", "The delayed-PING/stale-STOP, wraparound, lease, no-lease control and transport-loss cases each passed all supplied runs on all three boards. This supports those specific observed behaviors, not a general zero-loss or safety certification claim.", "",
        "Raw callback-count, stale-drop-count and stop-counter checks were also compared against case boundaries in every passing trace. Discrepancies (empty means none): " +
        str({name: findings for board in result["boards"].values() for name, findings in board["raw_consistency_checks"].items() if findings}), "",
        "## Timing from the on-board probe", "",
        "Percentiles use linear interpolation at `(n-1)*q`. Small n=10 timing samples are descriptive; tails are not statistically established. Failed scheduled trials are excluded only from timing summaries, and remain in the failure denominator above.", "",
        "| Board | Measurement (ms) | n | Min | Mean | p50 | p95 | Max |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    labels = {"lease_150ms_with_5hz_ping": "150 ms lease: active interval",
              "watchdog_without_ping": "Transport loss: active interval",
              "scheduled_preservation_and_stop_cancellation": "Scheduled callback lateness"}
    for board, data in result["boards"].items():
        for key, label in labels.items():
            m = data["timing_ms"].get(key, {})
            if m.get("n"):
                values = " | ".join(f"{m[k]:.3f}" for k in ("minimum", "mean", "p50", "p95", "maximum"))
                lines.append(f"| {board} | {label} | {m['n']} | {values} |")
    lines += ["", "`hold_ms` starts at the ACT callback. The watchdog deadline starts at the last received transport packet, including the immediate PING sent after ACT. Therefore hold_ms minus 500 is **not** a measured watchdog enforcement overshoot. Separately record the last receive timestamp before diagnosing poll latency from this difference.", "",
        "The lease is 150 ms and periodic PING starts about 200 ms after activation (plus the immediate observation PING). Add a 450 ms lease with 5 Hz PING, or a 150 ms lease with 20 Hz PING, to directly stress repeated heartbeat non-renewal before expiry. The present control still shows transport keepalives maintain a no-lease output for over two seconds.", "",
        "## Recorded scheduled-test failures", ""]
    for failure in result["failures"]:
        lines += [f"- **{failure['file']}**: `{failure['case']}`; {failure['error']}. RX ack states: {failure.get('rx_ack_values')}; watchdog counter states: {failure.get('watchdog_values')}."]
    lines += ["", "In the supplied ESP32 run07 and Pi run03 traces, the first scheduled command executes, the second ACT(seq=11) is logged as sent, but ack stays 10 and that callback is not observed; a later watchdog trip occurs. This is consistent with an unreceived/unapplied command, but sender logs alone cannot establish where it was lost or rejected.", "",
        "In RP2040 run04, ack reaches 11, STOP(seq=7) is sent, and a subsequent STATE omits ack while the watchdog counter is still unchanged. The output is zero and the queued callback does not appear. This unexpected receive-watermark transition is unresolved; it must not be called a clean pass or automatically attributed to Wi-Fi. Endpoint changes, interference, exact firmware identity and packet arrival need checking.", "",
        "The runner is single-shot and does not maintain keepalives during its one-second predicate waits; after a missing command/response it can itself allow the 500 ms watchdog to expire. These watchdog trips do not independently establish a watchdog defect. Preserve failures and distinguish delivery failures, observation failures, session resets and incorrect actuation in the next run.", "",
        "## Three-board synchronization estimate", ""]
    for name, sync in result["sync"].items():
        lines += [f"Input: `{name}`; seed={sync['seed']}, lead={sync['lead_ms']} ms, order={sync['order']}, injected jitter={sync['injected_jitter']}.", "",
            f"JSON/JSONL equality: **{sync['jsonl_identical_to_records']}**. Raw skew fields were recomputed; stored-summary mismatches: {sync['stored_summary_mismatches']}.", "",
            "| Mode | Poses | Mean estimated skew ms | p50 | p95 | p99 | Max | Observed Hz |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for mode, data in sync["modes"].items():
            m = data["estimated_skew_ms"]
            values = " | ".join(f"{m[k]:.3f}" for k in ("mean", "p50", "p95", "p99", "maximum"))
            lines.append(f"| {mode} | {m['n']} | {values} | {data['observed_interval_rate_hz']:.3f} |")
        lines += ["", f"Estimated mean reduction: **{sync.get('estimated_mean_reduction_pct', 0):.2f}%**. This is an exploratory comparison from one sequential run, not a paired randomized or multi-seed statistical result.", "",
            "| Mode / node | Counter discontinuities | Wrong values | Offset span ms | Negative mapped execution delays |", "| --- | --- | --- | --- | --- |"]
        for mode, data in sync["modes"].items():
            for node, m in data["nodes"].items():
                lines.append(f"| {mode} / {node} | {m['nonunit_counter_steps']} | {m['incorrect_values']} | {m['offset_span_ms']:.3f} | {m['negative_mapped_delays']} |")
    lines += ["", "**Do not present these numbers as independently measured physical skew.** Some mapped immediate callbacks precede the host dispatch time, an impossible physical latency that exposes clock-mapping bias. The same estimated offsets are used to schedule commands and to map execution back to master time, so the scheduled metric is partly self-referential. Directly validate offset error and physical edges before claiming physical synchronization improvement or an accuracy bound.", "",
        "The supplied synchronization trace has complete counters/values for 200 poses per mode per controller, but no execution-edge instrument, controlled delay distribution, repeated seeds, simultaneous scheduling-time offsets, source/build fingerprints or kernel packet capture. It cannot validate an injected-jitter horizon boundary, a sub-1.5 ms physical skew, or task-level swarm coordination.", "",
        "## Provenance and missing material", "",
        "Single-board files record the sending laptop's OS, revision and worktree status. That is not the Pi's OS/backend identity or proof of which MCU firmware was flashed. No completed operator report, sanitized flashed sketches, compiler/core/library versions, ELF/map files, build RAM/flash totals, actual GPIO backend, pin/wiring details, AP/load conditions or power-cycle labels were supplied. Fill those gaps using REPORT_TEMPLATE.md. The synchronization file itself does not record package versions or source revision.", "",
        "## What this supports for Stage 1", "",
        "- Preliminary live-board callback evidence for the tested sequence ordering and application-lease behavior, with measured local timing and an explicit CUSTOM-actuator scope.",
        "- A complete live SDK comparison showing lower estimated clock-mapped skew in one scheduled run; retain the estimator caveat and three functional failures.",
        "- Evidence of open reliability/measurement questions worth investigating. Not a claim that the framework, physical safety, middleware superiority or research novelty is established.", "",
        "## Next actions", "",
        "1. Supply the missing equipment/build/install information. Confirm MCU firmware and installed Python package identities.",
        "2. Investigate the three failures, especially RP2040's unexpected ack loss without a watchdog increment. Add source endpoints/session IDs and last-receive/execute timestamps to experiment logs before drawing a root-cause conclusion.",
        "3. Repeat lease tests with heartbeats occurring repeatedly before expiry. Measure watchdog timing relative to last received keepalive, separately from actuator activation.",
        "4. Obtain an independent common-clock GPIO measurement (instrument or separately calibrated observer). Repeat multiple seeds and alternate/interleave conditions; preserve every failure and distinguish actual delay injection from incidental Wi-Fi jitter.",
        "5. Test ordinary registered actuator paths and actual application hardware separately; this fixture exercises CUSTOM callbacks, not all HAL drivers.", "",
        "## Reproduce this audit", "", "```console", "python benchmarks/hardware/analyze_results.py --input hardware-result", "```", "",
        "REVIEW.json contains recomputed statistics, failure diagnostics and SHA-256 hashes for every supplied raw input. Raw files are not rewritten.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.input)
    (args.input / "REVIEW.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (args.input / "REVIEW.md").write_text(report(result), encoding="utf-8")
    print("Reviewed", len(result["inputs"]), "raw files; recorded failures:", len(result["failures"]))
