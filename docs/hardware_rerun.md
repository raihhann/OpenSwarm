# Bounded rerun after the scheduling/clock patch

After the first v2 campaign, a runner flag-lifecycle bug was identified in the
RP2040 failures. For the next step, use the smaller [targeted runner-fix rerun](hardware_rerun_runner_fix.md)
instead of repeating the whole campaign below. This preserves earlier results.

The old 32 raw files and benchmarks/hardware/results/campaign-01/REVIEW.* remain historical evidence.
Do not overwrite them. This patch fixes reproduced runner/estimator weaknesses;
the precise causes of all three physical failures are not proven from old logs.
In particular RP2040 run04's unexplained ACK disappearance requires confirmation.

## Software and publication status

- Arduino SwarmNode **0.4.3 is unchanged by this patch**. Keep the same flashed
  probe firmware. The existing local probe.ino edits are preserved.
- Linux slave **0.2.0 is unchanged by this patch**. Keep the same Pi probe process
  and installed slave package.
- The master SDK has a **prepared 0.2.1 patch**, not a published replacement.
  Published 0.2.0 remains available and installations are not modified remotely.
  The clock fix requires the new master code on the sending laptop. Other users
  can continue ordinary GPIO/sensor/control use with existing releases; their old
  clock estimator will not gain this fix until they upgrade.
- Hardware validation scripts changed. Copy the updated validate_node.py and
  sync_trial.py to the laptop; no editable package installation is required.

Install the supplied wheel on the Linux laptop, in its active test environment
(copy the built wheel from build/releases/master-0.2.1 first):

```bash
python -m pip install --upgrade ./openswarm_master-0.2.1-py3-none-any.whl
python -c 'import openswarm; print(openswarm.__version__, openswarm.__file__)'
```

Expect 0.2.1 and the active environment's installed package path. No PyPI/Arduino
tag has been pushed by this work. If released later, use the separate new
`master-v0.2.1` tag; do not change published 0.2.0 tags/artifacts.

## What changed and what a failure now means

The runner keeps one source socket throughout a board run, explicitly observes
a watchdog epoch reset between cases, and records source/destination endpoints
and phases. Scheduling waits send unsequenced keepalives every 100 ms. This
prevents the observer's wait from unintentionally starving the transport watchdog.
Scheduling/cancellation probes use a 500 ms horizon, allowing delivery confirmation
before the cancellation target. This is not evidence for performance at 30 ms.

The second scheduled ACT and cancellation STOP have at most three send attempts.
ACT retries use the same seq, so duplicates do not apply twice. The intentional
stale command's rejection is verified before those retries. Retries are reported
and are not silently counted as loss-free delivery. An ACK reset without a
watchdog increment fails immediately with unexpected_session_reset. Stop other
masters/GUI processes; this patch does not implement exclusive master ownership.

Clock calibration uses PING only, rejects reordered STATE, selects low-delay
samples and exposes conditional uncertainty. sync_actuate rejects stale/unknown
clock estimates before sending any command. The trial uses coherent snapshots
and frozen pretrial calibration for measurement, rather than remapping each pose
with its command ACK. It preserves negative point estimates and reports causal
interval violations instead of clamping them to apparently good values.
The clock bounds assume 1 ms timestamp quantization and 200 ppm maximum relative
drift; these assumptions are recorded and need independent hardware calibration.
This remains estimated callback skew, not a physical-edge measurement.

## Exact minimum rerun campaign

**Nine board runs plus six synchronization runs**, then review the evidence. This
is a pragmatic Stage 1 regression campaign, not a conference-prescribed sample
minimum or a statistical safety certification. No need to repeat all 30 old runs.
The current priority is finishing this engineering gate and understanding the
architecture before starting manuscript work. Then assess remaining driver,
resource and independent-timing evidence against the intended submission claims.

1. Use the same three probes. Record exact board/core/OS/backend/package versions,
   GPIOs, AP/load conditions and flashed build logs in the report template.
2. On the laptop, make `benchmarks/hardware/results/local/rerun` and run the validator **three times
   per board** with distinct names. Each run now contains seven cases, adding a
   450 ms lease with 5 Hz PING so heartbeats occur repeatedly before expiry.
3. Run the full 200-pose-per-mode synchronization trial for **seeds 2027, 2028,
   2029 at both lead 30 ms and lead 60 ms** (six sessions). Use the same quiet LAN
   first and record actual conditions. No controlled jitter is injected.
4. Return all JSON/JSONL, terminal failures and environment/build information.
   Any unexplained reset, missing/extra callback or causal-interval violation is
   a reason to investigate that run, not discard it and run until everything passes.

The prior IPs were ESP32 192.168.0.118, RP2040 192.168.0.170 and Pi
192.168.0.234. Check they still match before using these Linux laptop commands:

```bash
mkdir -p benchmarks/hardware/results/local/rerun
for run in 01 02 03; do
  python benchmarks/hardware/validate_node.py --ip 192.168.0.118 --output benchmarks/hardware/results/local/rerun/esp32-run${run}.json
  python benchmarks/hardware/validate_node.py --ip 192.168.0.170 --output benchmarks/hardware/results/local/rerun/rp2040-run${run}.json
  python benchmarks/hardware/validate_node.py --ip 192.168.0.234 --output benchmarks/hardware/results/local/rerun/rpi-run${run}.json
done
```

Then, with all probes running and the validator closed:

```bash
for lead in 30 60; do
  for seed in 2027 2028 2029; do
    python benchmarks/hardware/sync_trial.py \
      --node probe_esp32=192.168.0.118 \
      --node probe_rp2040=192.168.0.170 \
      --node probe_rpi=192.168.0.234 \
      --poses 200 --lead-ms "$lead" --seed "$seed" \
      --output "benchmarks/hardware/results/local/rerun/sync-lead${lead}-seed${seed}.json"
  done
done
```

This is 63 individual board cases and 2,400 multi-node pose batches. Expect roughly
15–30 minutes including setup/inspection on a responsive LAN; retain timeouts.
Do not treat these runs as a replacement for independent timing or actual actuator
testing. A Stage 1 manuscript can transparently present those as open validation
work, alongside the results and identified failure boundaries already available.
