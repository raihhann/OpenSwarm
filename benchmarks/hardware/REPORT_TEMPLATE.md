# OpenSwarm hardware validation report

Status: NOT YET RUN. Replace placeholders with observations; retain failed trials.
N/M = not measured; N/T = not tested. Do not replace either with zero.

## Provenance and conditions

- Operator / date / timezone:
- Tested commit + source changes/snapshot filename:
- Arduino library version + actual compiled source path:
- Master Python/package version + source path:
- Pi Python/package version + source path + actual GPIO backend:
- Router/AP model, band/channel, distance, other traffic:
- Laptop model/OS/CPU/power mode:
- Power supplies / resets / thermal conditions:
- Any deviation from the hardware README:

| Role | Exact board/model | Core/OS/compiler | Probe GPIO and header position | IP | Firmware/source identifier |
| --- | --- | --- | --- | --- | --- |
| ESP32 | | | | | |
| RP2040 | | | | | |
| Raspberry Pi | | | | | |
| Portenta H7 | Excluded: unsupported board path in current library | N/T | N/T | N/T | N/T |

## Build/resources

Attach complete build logs. Report bytes and named measurement method, not only percentages.

| Board/configuration | Flash bytes | Static RAM bytes | Physical SRAM bytes | Peak stack/heap (method or N/M) | Log/map file |
| --- | --- | --- | --- | --- | --- |
| ESP32 probe | | | | | |
| RP2040 probe | | | | | |
| Intended application, if tested | | | | | |

## Per-board functional results

Fill once per board, or add equivalent rows for each. Attach all run JSONs.

| Board | Case | Attempted trials | PASS / FAIL | Exact failure/counter discrepancy | Source files |
| --- | --- | --- | --- | --- | --- |
| | Delayed PING + stale STOP | | | | |
| | Sequence wraparound | | | | |
| | Scheduled preservation + STOP cancellation | | | | |
| | 150 ms lease + 5 Hz PING | | | | |
| | No lease + 5 Hz PING | | | | |
| | Transport loss | | | | |

## On-board timing, not physical stopping time

Summaries may be left for analysis from the attached raw JSON. State the sample count.
Record early stops, long delays, missing telemetry and resets separately.

| Board/case | n | min | mean | p50 | p95 | max | Target ms | Measurement resolution/method |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ESP32 lease | | | | | | | 150 | board callback millis |
| RP2040 lease | | | | | | | 150 | board callback millis |
| RPi lease | | | | | | | 150 | software monotonic callback |
| Watchdog, per board | | | | | | | >500 | |
| Scheduled lateness, per board | | | | | | | 0 excess | |

## Multi-board timing estimate

Independent timing reference available: **No** (unless a separately described instrument
was actually used). These estimates reuse the framework clock-offset estimator.

| Conditions / seed / lead ms | Mode | Complete poses / requested | Estimated mean/p50/p95/p99/max skew ms | Failures | JSON + JSONL files |
| --- | --- | --- | --- | --- | --- |
| | Immediate | /200 | | | |
| | Scheduled | /200 | | | |

- Actual run duration/rate:
- RTT/offset behavior, asymmetry/drift observations:
- Any Wi-Fi/CPU load, with exact reproduction steps:
- Controlled delay injection: None / describe actual method and measured distribution.
- Physical inter-controller actuation skew: N/M unless independently measured.

## Actual application actuators (separate from CUSTOM probe)

| Board / actuator / unloaded fixture | Normal operation | STOP | Lease | Transport loss | Physical observation / measurement method | Blocking/other failures |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |

## Failures, exclusions and attachments

- List every failed/partial run and why it failed; no silent removal:
- Power-cycle/reconnect results:
- Unsupported features / N/T items:
- Photos/video filenames (if any):
- Raw JSON / JSONL inventory and expected trial counts:
- Sanitized firmware, build logs/maps and source snapshot filenames:
- Questions or surprising observations to investigate:

## Review outcome (to be completed after evidence review)

- Verified engineering behaviors:
- Claims supported by this evidence:
- Claims requiring qualification or rejection:
- Remaining submission/hardware work:
