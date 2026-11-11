# Hardware evidence review

This review preserves the supplied raw files and includes every recorded failure. Measurements are probe callback/telemetry observations on user-reported physical boards, not independently measured GPIO edges or motor motion.

## Trial inventory and functional outcomes

| Board | Run files | Case PASS | Case FAIL | Scheduled test PASS / attempted |
| --- | --- | --- | --- | --- |
| esp32 | 10 | 59 | 1 | 9 / 10 |
| rp2040 | 10 | 59 | 1 | 9 / 10 |
| rpi | 10 | 59 | 1 | 9 / 10 |

The delayed-PING/stale-STOP, wraparound, lease, no-lease control and transport-loss cases each passed all supplied runs on all three boards. This supports those specific observed behaviors, not a general zero-loss or safety certification claim.

Raw callback-count, stale-drop-count and stop-counter checks were also compared against case boundaries in every passing trace. Discrepancies (empty means none): {}

## Timing from the on-board probe

Percentiles use linear interpolation at `(n-1)*q`. Small n=10 timing samples are descriptive; tails are not statistically established. Failed scheduled trials are excluded only from timing summaries, and remain in the failure denominator above.

| Board | Measurement (ms) | n | Min | Mean | p50 | p95 | Max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| esp32 | 150 ms lease: active interval | 10 | 150.000 | 150.700 | 151.000 | 151.000 | 151.000 |
| esp32 | Transport loss: active interval | 10 | 502.000 | 503.000 | 503.000 | 504.000 | 504.000 |
| esp32 | Scheduled callback lateness | 9 | 0.000 | 0.667 | 1.000 | 1.000 | 1.000 |
| rp2040 | 150 ms lease: active interval | 10 | 150.000 | 151.800 | 152.000 | 153.100 | 154.000 |
| rp2040 | Transport loss: active interval | 10 | 517.000 | 521.600 | 522.500 | 523.550 | 524.000 |
| rp2040 | Scheduled callback lateness | 9 | 0.000 | 2.222 | 2.000 | 4.000 | 4.000 |
| rpi | 150 ms lease: active interval | 10 | 152.369 | 153.829 | 154.073 | 154.544 | 154.608 |
| rpi | Transport loss: active interval | 10 | 502.021 | 504.514 | 502.629 | 509.919 | 509.942 |
| rpi | Scheduled callback lateness | 9 | 0.000 | 5.889 | 6.000 | 10.000 | 10.000 |

`hold_ms` starts at the ACT callback. The watchdog deadline starts at the last received transport packet, including the immediate PING sent after ACT. Therefore hold_ms minus 500 is **not** a measured watchdog enforcement overshoot. Separately record the last receive timestamp before diagnosing poll latency from this difference.

The lease is 150 ms and periodic PING starts about 200 ms after activation (plus the immediate observation PING). Add a 450 ms lease with 5 Hz PING, or a 150 ms lease with 20 Hz PING, to directly stress repeated heartbeat non-renewal before expiry. The present control still shows transport keepalives maintain a no-lease output for over two seconds.

## Recorded scheduled-test failures

- **esp32-run07.json**: `scheduled_preservation_and_stop_cancellation`; Expected STATE not observed; retain packet log, do not infer success. RX ack states: [10, None]; watchdog counter states: [12, 13].
- **rp2040-run04.json**: `scheduled_preservation_and_stop_cancellation`; Expected STATE not observed; retain packet log, do not infer success. RX ack states: [None, 10, 11]; watchdog counter states: [6, 7].
- **rpi-run03.json**: `scheduled_preservation_and_stop_cancellation`; Expected STATE not observed; retain packet log, do not infer success. RX ack states: [10, None]; watchdog counter states: [4, 5].

In the supplied ESP32 run07 and Pi run03 traces, the first scheduled command executes, the second ACT(seq=11) is logged as sent, but ack stays 10 and that callback is not observed; a later watchdog trip occurs. This is consistent with an unreceived/unapplied command, but sender logs alone cannot establish where it was lost or rejected.

In RP2040 run04, ack reaches 11, STOP(seq=7) is sent, and a subsequent STATE omits ack while the watchdog counter is still unchanged. The output is zero and the queued callback does not appear. This unexpected receive-watermark transition is unresolved; it must not be called a clean pass or automatically attributed to Wi-Fi. Endpoint changes, interference, exact firmware identity and packet arrival need checking.

The runner is single-shot and does not maintain keepalives during its one-second predicate waits; after a missing command/response it can itself allow the 500 ms watchdog to expire. These watchdog trips do not independently establish a watchdog defect. Preserve failures and distinguish delivery failures, observation failures, session resets and incorrect actuation in the next run.

## Three-board synchronization estimate

Input: `sync-lead30-seed2027.json`; seed=2027, lead=30.0 ms, order=['scheduled', 'immediate'], injected jitter=False.

JSON/JSONL equality: **True**. Raw skew fields were recomputed; stored-summary mismatches: [].

| Mode | Poses | Mean estimated skew ms | p50 | p95 | p99 | Max | Observed Hz |
| --- | --- | --- | --- | --- | --- | --- | --- |
| scheduled | 200 | 8.194 | 4.618 | 35.190 | 44.503 | 46.908 | 9.806 |
| immediate | 200 | 25.568 | 18.383 | 82.111 | 91.607 | 103.321 | 9.863 |

Estimated mean reduction: **67.95%**. This is an exploratory comparison from one sequential run, not a paired randomized or multi-seed statistical result.

| Mode / node | Counter discontinuities | Wrong values | Offset span ms | Negative mapped execution delays |
| --- | --- | --- | --- | --- |
| scheduled / probe_esp32 | 0 | 0 | 28.459 | 0 |
| scheduled / probe_rp2040 | 0 | 0 | 97.253 | 0 |
| scheduled / probe_rpi | 0 | 0 | 27.932 | 0 |
| immediate / probe_esp32 | 0 | 0 | 29.413 | 76 |
| immediate / probe_rp2040 | 0 | 0 | 64.406 | 51 |
| immediate / probe_rpi | 0 | 0 | 26.512 | 103 |

**Do not present these numbers as independently measured physical skew.** Some mapped immediate callbacks precede the host dispatch time, an impossible physical latency that exposes clock-mapping bias. The same estimated offsets are used to schedule commands and to map execution back to master time, so the scheduled metric is partly self-referential. Directly validate offset error and physical edges before claiming physical synchronization improvement or an accuracy bound.

The supplied synchronization trace has complete counters/values for 200 poses per mode per controller, but no execution-edge instrument, controlled delay distribution, repeated seeds, simultaneous scheduling-time offsets, source/build fingerprints or kernel packet capture. It cannot validate an injected-jitter horizon boundary, a sub-1.5 ms physical skew, or task-level swarm coordination.

## Provenance and missing material

Single-board files record the sending laptop's OS, revision and worktree status. That is not the Pi's OS/backend identity or proof of which MCU firmware was flashed. No completed operator report, sanitized flashed sketches, compiler/core/library versions, ELF/map files, build RAM/flash totals, actual GPIO backend, pin/wiring details, AP/load conditions or power-cycle labels were supplied. Fill those gaps using REPORT_TEMPLATE.md. The synchronization file itself does not record package versions or source revision.

## What this supports for Stage 1

- Preliminary live-board callback evidence for the tested sequence ordering and application-lease behavior, with measured local timing and an explicit CUSTOM-actuator scope.
- A complete live SDK comparison showing lower estimated clock-mapped skew in one scheduled run; retain the estimator caveat and three functional failures.
- Evidence of open reliability/measurement questions worth investigating. Not a claim that the framework, physical safety, middleware superiority or research novelty is established.

## Next actions

1. Supply the missing equipment/build/install information. Confirm MCU firmware and installed Python package identities.
2. Investigate the three failures, especially RP2040's unexpected ack loss without a watchdog increment. Add source endpoints/session IDs and last-receive/execute timestamps to experiment logs before drawing a root-cause conclusion.
3. Repeat lease tests with heartbeats occurring repeatedly before expiry. Measure watchdog timing relative to last received keepalive, separately from actuator activation.
4. Obtain an independent common-clock GPIO measurement (instrument or separately calibrated observer). Repeat multiple seeds and alternate/interleave conditions; preserve every failure and distinguish actual delay injection from incidental Wi-Fi jitter.
5. Test ordinary registered actuator paths and actual application hardware separately; this fixture exercises CUSTOM callbacks, not all HAL drivers.

## Reproduce this audit

```console
python benchmarks/hardware/analyze_results.py --input hardware-result
```

REVIEW.json contains recomputed statistics, failure diagnostics and SHA-256 hashes for every supplied raw input. Raw files are not rewritten.
