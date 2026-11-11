# Hardware results review

All supplied raw inputs are preserved. This report distinguishes recorded outcomes, test-instrument defects, partial trials and independent physical evidence.

## Board runs

| Board | Run files | Recorded PASS | Recorded FAIL | Runner false-alarm aborts |
| --- | --- | --- | --- | --- |
| esp32 | 3 | 21 | 0 | 0 |
| rp2040 | 3 | 9 | 12 | 12 |
| rpi | 3 | 21 | 0 | 0 |

Raw passing-case callback/drop/stop-counter consistency discrepancies: {}

## RP2040 failure diagnosis

**12 failures match a reproduced runner defect.** During the intentional watchdog-reset phase, an old positive ACK set Session.armed. The old runner did not clear it on the new watchdog epoch. The first active-phase STATE without ACK then triggered unexpected_session_reset even though no positive ACK had yet been observed in that case.

This is a false reset alarm in the test runner. The premature cleanup STOP then aborted the experiment, so the remaining actuator behavior is untested. Keep each original FAIL and mark it instrument-aborted; do not convert it to PASS or infer a bad RP2040 firmware implementation.

The fix clears arming on a watchdog transition and on entry to a new case, and only arms after a positive ACK in the active phase. Regression coverage also verifies a genuine ACK disappearance after that point still fails.

- `rp2040-run01.json` / `scheduled_preservation_and_stop_cancellation`: runner false alarm; rerun required. Recorded error: ACK disappeared without a watchdog event; check endpoints, competing masters and firmware
- `rp2040-run01.json` / `lease_150ms_with_5hz_ping`: runner false alarm; rerun required. Recorded error: ACK disappeared without a watchdog event; check endpoints, competing masters and firmware
- `rp2040-run01.json` / `lease_450ms_with_5hz_ping`: runner false alarm; rerun required. Recorded error: ACK disappeared without a watchdog event; check endpoints, competing masters and firmware
- `rp2040-run02.json` / `sequence_wraparound`: runner false alarm; rerun required. Recorded error: ACK disappeared without a watchdog event; check endpoints, competing masters and firmware
- `rp2040-run02.json` / `scheduled_preservation_and_stop_cancellation`: runner false alarm; rerun required. Recorded error: ACK disappeared without a watchdog event; check endpoints, competing masters and firmware
- `rp2040-run02.json` / `lease_450ms_with_5hz_ping`: runner false alarm; rerun required. Recorded error: ACK disappeared without a watchdog event; check endpoints, competing masters and firmware
- `rp2040-run02.json` / `no_lease_with_5hz_ping`: runner false alarm; rerun required. Recorded error: ACK disappeared without a watchdog event; check endpoints, competing masters and firmware
- `rp2040-run03.json` / `sequence_wraparound`: runner false alarm; rerun required. Recorded error: ACK disappeared without a watchdog event; check endpoints, competing masters and firmware
- `rp2040-run03.json` / `scheduled_preservation_and_stop_cancellation`: runner false alarm; rerun required. Recorded error: ACK disappeared without a watchdog event; check endpoints, competing masters and firmware
- `rp2040-run03.json` / `lease_150ms_with_5hz_ping`: runner false alarm; rerun required. Recorded error: ACK disappeared without a watchdog event; check endpoints, competing masters and firmware
- `rp2040-run03.json` / `lease_450ms_with_5hz_ping`: runner false alarm; rerun required. Recorded error: ACK disappeared without a watchdog event; check endpoints, competing masters and firmware
- `rp2040-run03.json` / `no_lease_with_5hz_ping`: runner false alarm; rerun required. Recorded error: ACK disappeared without a watchdog event; check endpoints, competing masters and firmware

## Local probe timing

| Board | Callback measurement (ms) | n | Min | Mean | p50 | p95 | Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| esp32 | 150 ms lease | 3 | 150.000 | 150.333 | 150.000 | 150.900 | 151.000 |
| esp32 | 450 ms lease with intervening PINGs | 3 | 450.000 | 450.000 | 450.000 | 450.000 | 450.000 |
| esp32 | Transport loss: active interval | 3 | 502.000 | 503.667 | 504.000 | 504.900 | 505.000 |
| esp32 | Scheduled callback lateness | 3 | 0.000 | 0.333 | 0.000 | 0.900 | 1.000 |
| rp2040 | 150 ms lease | 1 | 153.000 | 153.000 | 153.000 | 153.000 | 153.000 |
| rp2040 | Transport loss: active interval | 3 | 518.000 | 520.667 | 521.000 | 522.800 | 523.000 |
| rpi | 150 ms lease | 3 | 153.946 | 154.171 | 153.999 | 154.512 | 154.569 |
| rpi | 450 ms lease with intervening PINGs | 3 | 451.110 | 451.749 | 451.422 | 452.587 | 452.716 |
| rpi | Transport loss: active interval | 3 | 501.872 | 502.614 | 502.810 | 503.124 | 503.159 |
| rpi | Scheduled callback lateness | 3 | 2.000 | 4.667 | 4.000 | 7.600 | 8.000 |

Only completed passing cases contribute timings. Interrupted RP2040 cases are absent from the relevant distributions. These are local callback intervals/quantized timestamps, not measured GPIO edges, motor stopping times or established tail guarantees. Percentiles use linear interpolation at (n-1)*q.

Watchdog hold_ms begins at ACT execution, while its deadline begins at the last received transport packet, including the following PING. Subtracting 500 from hold_ms does not isolate watchdog enforcement overshoot.

## Synchronization sessions

| File | Outcome | Saved poses | Lead ms | Seed | Order |
| --- | --- | --- | --- | --- | --- |
| sync-lead30-seed2027_01.json | FAIL / partial | 109 | 30.0 | 2027 | None |
| sync-lead30-seed2027_02.json | complete | 400 | 30.0 | 2027 | ['scheduled', 'immediate'] |
| sync-lead30-seed2027_03.json | complete | 400 | 30.0 | 2027 | ['scheduled', 'immediate'] |
| sync-lead30-seed2027_04.json | complete | 400 | 30.0 | 2027 | ['scheduled', 'immediate'] |
| sync-lead30-seed2027_05.json | complete | 400 | 30.0 | 2027 | ['scheduled', 'immediate'] |
| sync-lead30-seed2027_06.json | complete | 400 | 30.0 | 2027 | ['scheduled', 'immediate'] |

Failure retained in `sync-lead30-seed2027_01.json`: Missing execution telemetry; no missing pose may be silently discarded. The partial JSONL establishes only the completed poses; the failed pose/node cannot be identified conclusively from an exception file that lacks final per-node diagnostics.

Completed sessions are not substitutes for a reliability denominator: the failed attempt remains recorded. Repeated seed/lead values are replicated sessions of that configuration, not the planned different-seed/30-vs-60-ms sweep.

| Complete file | Mode | n | Estimated mean skew ms | p50 | p95 | p99 | Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sync-lead30-seed2027_02.json | scheduled | 200 | 8.273 | 5.066 | 40.343 | 54.303 | 58.293 |
| sync-lead30-seed2027_02.json | immediate | 200 | 19.344 | 12.934 | 70.034 | 82.944 | 86.293 |
| sync-lead30-seed2027_03.json | scheduled | 200 | 11.692 | 5.776 | 52.272 | 58.242 | 77.222 |
| sync-lead30-seed2027_03.json | immediate | 200 | 23.090 | 16.447 | 82.384 | 101.355 | 117.222 |
| sync-lead30-seed2027_04.json | scheduled | 200 | 12.977 | 5.789 | 56.757 | 70.727 | 73.707 |
| sync-lead30-seed2027_04.json | immediate | 200 | 23.291 | 16.211 | 83.336 | 99.351 | 113.211 |
| sync-lead30-seed2027_05.json | scheduled | 200 | 10.862 | 5.259 | 48.239 | 55.239 | 62.189 |
| sync-lead30-seed2027_05.json | immediate | 200 | 23.069 | 15.741 | 82.189 | 88.389 | 129.741 |
| sync-lead30-seed2027_06.json | scheduled | 200 | 10.132 | 5.260 | 49.310 | 78.300 | 87.260 |
| sync-lead30-seed2027_06.json | immediate | 200 | 22.086 | 14.469 | 82.310 | 87.282 | 91.260 |

Recomputed causal-interval violations in saved poses: **0**. Non-unit callback-counter steps: **0**. Wrong recorded values: **0**. Summed per-mode watchdog-counter spans: **0**.

Complete-file JSON and JSONL agree: True. Stored numerical summary mismatches: {}.

The saved v2 sessions use master 0.2.1 and frozen pretrial calibration. Zero causal-interval violations means the observations are consistent with the declared conditional clock bounds. Negative point estimates can remain inside those bounds. This does not establish true clock-offset error or independent physical synchronization accuracy; drift assumptions and external GPIO-edge timing still need validation.

## Minimal next step

Update validate_node.py and rerun the three RP2040 board trials into a NEW folder. Leave ESP32/Pi firmware and all published packages unchanged; their completed board tests need not be repeated for this runner-only fix. Retain the 12 interrupted cases as such.

Add one three-board synchronization session at lead 60 ms, seed 2028, 200 poses per mode. Seed 2028 reverses the mode order used in the supplied sessions. This adds a missing condition and a fresh completion check without repeating the entire campaign. Retain the earlier failed attempt. Recurrent timeouts require per-node failure diagnostics before attributing a cause.

## Evidence boundaries and missing material

The dataset contains probe CUSTOM callbacks and software timing estimates. Ordinary actuator stop behavior, actual motor/servo dynamics, complete target RAM/flash/stack measurements, authenticated sessions and peer-to-peer robot coordination are not validated here. Supply board/core/firmware build identities, installed package paths, Pi GPIO backend, pin/wiring and AP/load conditions using REPORT_TEMPLATE.md.

The previous ten-runs-per-board dataset is not present in this supplied directory. This review describes only the current input inventory and does not silently merge earlier evidence.

## Reproduce

```console
python benchmarks/hardware/analyze_results.py --input hardware-result
```

REVIEW.json includes per-file diagnostics, recomputed descriptive statistics and SHA-256 hashes of all raw inputs. Raw JSON/JSONL files are not rewritten.
