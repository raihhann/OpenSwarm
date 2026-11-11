# Targeted rerun after the RP2040 test-detector fix

This is a test-runner-only correction. Arduino SwarmNode 0.4.3, Linux slave 0.2.0
and installed master 0.2.1 do not change. No board reflashing or package upgrade
is needed. Update validate_node.py and sync_trial.py on the Linux laptop after
committing/pushing these file changes and pulling them there.

The supplied three ESP32 and three Pi runs each completed all 21 board cases.
All twelve recorded RP2040 failures have the premature reset-detector signature:
the reset phase observed an old ACK, and the active case aborted on an ordinary
ACK-less STATE before any positive ACK was observed in that case. This interrupted
the tests and does not establish either passing or failing remaining RP2040 behavior.
The corrected detector clears its arming state at the epoch/case boundary and
still rejects genuine subsequent ACK loss. Regression tests cover both paths.

Keep the existing benchmarks/hardware/results/campaign-02 folder unchanged. Run just three new RP2040
trials, using the same probe firmware and active Linux laptop environment:

```bash
cd ~/OpenSwarm
git pull
mkdir -p benchmarks/hardware/results/local/rp2040-fix
for run in 01 02 03; do
  python benchmarks/hardware/validate_node.py \
    --ip 192.168.0.170 \
    --output "benchmarks/hardware/results/local/rp2040-fix/rp2040-run${run}.json"
done
```

Check the RP2040 still has that IP. Stop all other control programs while the
validator runs. Do not rerun ESP32/Pi board cases for this detector-only change.

The six supplied synchronization attempts all used lead 30 ms and seed 2027.
Five completed; one timed out after 109 saved poses and remains a failed attempt.
The completed raw records and JSONL agree; their conditional causal-interval
checks pass. Those estimates are not independently measured physical skew.

After the three RP2040 runs, keep all three probe nodes running and add just one
session at lead 60 ms / seed 2028 (opposite mode order to the supplied sessions):

```bash
python benchmarks/hardware/sync_trial.py \
  --node probe_esp32=192.168.0.118 \
  --node probe_rp2040=192.168.0.170 \
  --node probe_rpi=192.168.0.234 \
  --poses 200 --lead-ms 60 --seed 2028 \
  --output benchmarks/hardware/results/local/rp2040-fix/sync-lead60-seed2028.json
```

Confirm all three IPs first. The updated sync script saves each node's last
snapshot and expected callback count on timeout, so another incomplete trial
will have more useful failure evidence. Send all new JSON/JSONL and failures.
This is four additional runs, not a repeat of the full campaign. Do not delete
the earlier failures or replace them with passing reruns.
