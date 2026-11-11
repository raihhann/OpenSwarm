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


def premature_reset_alarm(data, case):
    """An ACK cannot disappear in a new case before any ACK was observed there."""
    if case.get("error_kind") != "unexpected_session_reset":
        return False
    phase = case.get("phase")
    observed = [p["packet"] for p in data["packet_log"] if p.get("phase") == phase and
                p["direction"] == "rx" and p["packet"].get("type") == "STATE"]
    reset = [p["packet"] for p in data["packet_log"] if p.get("phase") == phase + "/reset" and
             p["direction"] == "rx" and p["packet"].get("type") == "STATE"]
    return bool(observed and reset and not any(p.get("ack") for p in observed) and
                any(p.get("ack") for p in reset) and not reset[-1].get("ack") and
                reset[-1].get("wd_trips", 0) > reset[0].get("wd_trips", 0))


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
        drop_states = states
        if name == "scheduled_preservation_and_stop_cancellation" and data.get("schema_version", 1) >= 2:
            # Delivery retries after the verified stale injection may legitimately
            # add duplicate drops. Audit the injection before ACT(seq=11).
            retry_start = next((i for i in range(start + 1, end) if packets[i]["direction"] == "tx" and
                                packets[i]["packet"].get("cmd") == "ACT" and packets[i]["packet"].get("seq") == 11), end)
            drop_states = [p["packet"] for p in packets[start:retry_start] if p["direction"] == "rx" and p["packet"].get("type") == "STATE"]
        if not drop_states or max(p.get("seq_drop", 0) for p in drop_states) != base.get("seq_drop", 0) + drop_increment:
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
                    failure = dict(file=path.name, case=case["name"], error=case.get("error"),
                                   error_kind=case.get("error_kind"), phase=case.get("phase"),
                                   premature_reset_detector=premature_reset_alarm(data, case))
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
                    jsonl_identical_to_records=raw_lines == data["records"] if "records" in data else None,
                    partial_only="records" not in data, master_version=data.get("master_version"),
                    lead_ms=data.get("lead_ms"), seed=data.get("seed"), order=data.get("order"),
                    injected_jitter=data.get("injected_jitter"), stored_summary_mismatches=[])
        records = data.get("records", raw_lines or [])
        sync["record_count"] = len(records)
        for mode in ("scheduled", "immediate"):
            rows = [r for r in records if r["mode"] == mode]
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
                    if "execution_master_interval_ms" in node:
                        arrays["causal_interval_violations"].append(node["execution_master_interval_ms"][1] < row["host_dispatch_mono_s"] * 1000)
                    live = node.get("live_snapshot", {})
                    arrays["watchdog_counter"].append(live.get("wd_trips", 0))
            measured = stats(skews)
            stored = data.get("estimated_skew_ms", {}).get(mode, {})
            for key in ("mean", "p50", "p95", "p99", "maximum"):
                if "records" in data and (key not in stored or abs(stored[key] - measured[key]) > 1e-6):
                    sync["stored_summary_mismatches"].append(mode + "/" + key)
            node_summary = {}
            for name, arrays in per_node.items():
                node_summary[name] = dict(
                    act_first=arrays["acts"][0], act_last=arrays["acts"][-1],
                    nonunit_counter_steps=sum(b != a + 1 for a, b in zip(arrays["acts"], arrays["acts"][1:])),
                    incorrect_values=sum(value != row["pose"] + 1 for value, row in zip(arrays["values"], rows)),
                    offset_span_ms=max(arrays["offset_ms"]) - min(arrays["offset_ms"]),
                    rtt_ms=stats(arrays["rtt_ms"]), mapped_delay_ms=stats(arrays["mapped_delay_ms"]),
                    negative_mapped_delays=sum(v < 0 for v in arrays["mapped_delay_ms"]),
                    causal_interval_violations=sum(arrays["causal_interval_violations"]),
                    watchdog_counter_span=max(arrays["watchdog_counter"]) - min(arrays["watchdog_counter"]))
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
    lines = ["# Hardware results review", "",
        "All supplied raw inputs are preserved. This report distinguishes recorded outcomes, test-instrument defects, partial trials and independent physical evidence.", "",
        "## Board runs", "",
        "| Board | Run files | Recorded PASS | Recorded FAIL | Runner false-alarm aborts |",
        "| --- | --- | --- | --- | --- |"]
    for name, board in result["boards"].items():
        aborted = sum(f.get("premature_reset_detector", False) for f in result["failures"] if f["file"].startswith(name + "-"))
        lines.append(f"| {name} | {board['files']} | {board['statuses'].get('PASS', 0)} | {board['statuses'].get('FAIL', 0)} | {aborted} |")
    discrepancies = {name: findings for board in result["boards"].values()
                     for name, findings in board["raw_consistency_checks"].items() if findings}
    lines += ["", "Raw passing-case callback/drop/stop-counter consistency discrepancies: " + str(discrepancies), "",
        "## RP2040 failure diagnosis", ""]
    alarms = [f for f in result["failures"] if f.get("premature_reset_detector")]
    if alarms:
        lines += [f"**{len(alarms)} failures match a reproduced runner defect.** During the intentional watchdog-reset phase, an old positive ACK set Session.armed. The old runner did not clear it on the new watchdog epoch. The first active-phase STATE without ACK then triggered unexpected_session_reset even though no positive ACK had yet been observed in that case.", "",
            "This is a false reset alarm in the test runner. The premature cleanup STOP then aborted the experiment, so the remaining actuator behavior is untested. Keep each original FAIL and mark it instrument-aborted; do not convert it to PASS or infer a bad RP2040 firmware implementation.", "",
            "The fix clears arming on a watchdog transition and on entry to a new case, and only arms after a positive ACK in the active phase. Regression coverage also verifies a genuine ACK disappearance after that point still fails.", ""]
    else:
        lines += ["No supplied failure matched the premature-reset-detector signature.", ""]
    for failure in result["failures"]:
        classification = "runner false alarm; rerun required" if failure.get("premature_reset_detector") else "unresolved"
        lines.append(f"- `{failure['file']}` / `{failure['case']}`: {classification}. Recorded error: {failure['error']}")
    lines += ["", "## Local probe timing", "",
        "| Board | Callback measurement (ms) | n | Min | Mean | p50 | p95 | Max |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    labels = {"lease_150ms_with_5hz_ping": "150 ms lease",
              "lease_450ms_with_5hz_ping": "450 ms lease with intervening PINGs",
              "watchdog_without_ping": "Transport loss: active interval",
              "scheduled_preservation_and_stop_cancellation": "Scheduled callback lateness"}
    for board, data in result["boards"].items():
        for key, label in labels.items():
            measured = data["timing_ms"].get(key, {})
            if measured.get("n"):
                values = " | ".join(f"{measured[k]:.3f}" for k in ("minimum", "mean", "p50", "p95", "maximum"))
                lines.append(f"| {board} | {label} | {measured['n']} | {values} |")
    lines += ["", "Only completed passing cases contribute timings. Interrupted RP2040 cases are absent from the relevant distributions. These are local callback intervals/quantized timestamps, not measured GPIO edges, motor stopping times or established tail guarantees. Percentiles use linear interpolation at (n-1)*q.", "",
        "Watchdog hold_ms begins at ACT execution, while its deadline begins at the last received transport packet, including the following PING. Subtracting 500 from hold_ms does not isolate watchdog enforcement overshoot.", "",
        "## Synchronization sessions", "",
        "| File | Outcome | Saved poses | Lead ms | Seed | Order |",
        "| --- | --- | --- | --- | --- | --- |"]
    sync_errors = []
    for name, sync in result["sync"].items():
        outcome = "FAIL / partial" if sync["partial_only"] or sync["status"] == "FAIL" else "complete"
        lines.append(f"| {name} | {outcome} | {sync['record_count']} | {sync['lead_ms']} | {sync['seed']} | {sync['order']} |")
        if sync.get("error"):
            sync_errors += [f"Failure retained in `{name}`: {sync['error']}. The partial JSONL establishes only the completed poses; the failed pose/node cannot be identified conclusively from an exception file that lacks final per-node diagnostics."]
    lines += [""] + sync_errors + ["", "Completed sessions are not substitutes for a reliability denominator: the failed attempt remains recorded. Repeated seed/lead values are replicated sessions of that configuration, not the planned different-seed/30-vs-60-ms sweep.", "",
        "| Complete file | Mode | n | Estimated mean skew ms | p50 | p95 | p99 | Max |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, sync in result["sync"].items():
        if sync["partial_only"] or sync["status"] == "FAIL":
            continue
        for mode, data in sync["modes"].items():
            measured = data["estimated_skew_ms"]
            values = " | ".join(f"{measured[k]:.3f}" for k in ("mean", "p50", "p95", "p99", "maximum"))
            lines.append(f"| {name} | {mode} | {measured['n']} | {values} |")
    all_nodes = [node for sync in result["sync"].values() for mode in sync["modes"].values() for node in mode["nodes"].values()]
    lines += ["", f"Recomputed causal-interval violations in saved poses: **{sum(n['causal_interval_violations'] for n in all_nodes)}**. Non-unit callback-counter steps: **{sum(n['nonunit_counter_steps'] for n in all_nodes)}**. Wrong recorded values: **{sum(n['incorrect_values'] for n in all_nodes)}**. Summed per-mode watchdog-counter spans: **{sum(n['watchdog_counter_span'] for n in all_nodes)}**.", "",
        "Complete-file JSON and JSONL agree: " + str(all(s["jsonl_identical_to_records"] for s in result["sync"].values() if not s["partial_only"])) +
        ". Stored numerical summary mismatches: " + str({name: s["stored_summary_mismatches"] for name, s in result["sync"].items() if s["stored_summary_mismatches"]}) + ".", "",
        "The saved v2 sessions use master 0.2.1 and frozen pretrial calibration. Zero causal-interval violations means the observations are consistent with the declared conditional clock bounds. Negative point estimates can remain inside those bounds. This does not establish true clock-offset error or independent physical synchronization accuracy; drift assumptions and external GPIO-edge timing still need validation.", "",
        "## Minimal next step", "",
        "Update validate_node.py and rerun the three RP2040 board trials into a NEW folder. Leave ESP32/Pi firmware and all published packages unchanged; their completed board tests need not be repeated for this runner-only fix. Retain the 12 interrupted cases as such.", "",
        "Add one three-board synchronization session at lead 60 ms, seed 2028, 200 poses per mode. Seed 2028 reverses the mode order used in the supplied sessions. This adds a missing condition and a fresh completion check without repeating the entire campaign. Retain the earlier failed attempt. Recurrent timeouts require per-node failure diagnostics before attributing a cause.", "",
        "## Evidence boundaries and missing material", "",
        "The dataset contains probe CUSTOM callbacks and software timing estimates. Ordinary actuator stop behavior, actual motor/servo dynamics, complete target RAM/flash/stack measurements, authenticated sessions and peer-to-peer robot coordination are not validated here. Supply board/core/firmware build identities, installed package paths, Pi GPIO backend, pin/wiring and AP/load conditions using REPORT_TEMPLATE.md.", "",
        "The previous ten-runs-per-board dataset is not present in this supplied directory. This review describes only the current input inventory and does not silently merge earlier evidence.", "",
        "## Reproduce", "", "```console", "python benchmarks/hardware/analyze_results.py --input hardware-result", "```", "",
        "REVIEW.json includes per-file diagnostics, recomputed descriptive statistics and SHA-256 hashes of all raw inputs. Raw JSON/JSONL files are not rewritten.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.input)
    (args.input / "REVIEW.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (args.input / "REVIEW.md").write_text(report(result), encoding="utf-8")
    print("Reviewed", len(result["inputs"]), "raw files; recorded failures:", len(result["failures"]))
