# Hardware validation with your available equipment

**Updated runners:** the scheduling/clock patch requires master SDK **0.2.1**,
currently prepared as a local wheel. Follow [the bounded rerun instructions](../../docs/hardware_rerun.md)
for installation and the nine-board-run/six-sync-run campaign. Arduino 0.4.3 and
Linux slave 0.2.0 remain unchanged. Original raw results must be retained separately.

Equipment: ESP32, an Arduino RP2040 board, Raspberry Pi, Linux laptop, and Portenta
H7; no oscilloscope or logic analyzer. Run the laptop as master and the Pi as a
slave. Check the RP2040 model: Nano RP2040 Connect and Pico W have supported Wi-Fi
paths; a non-Wi-Fi Pico cannot run these network tests unchanged. Portenta H7 has
no board-selection/HAL path in this version of SwarmNode. Leave it out of this
campaign; Portenta X8 Linux support is a different platform.

Start with the unloaded probe fixture below. It measures actual board callbacks
and GPIO requests, not servo motion or stopping distance. No robot motion is
needed. Use one controller at a time initially, and stop all other masters, GUIs,
CLI sessions and emulators so they cannot replace the test session.

**Start with ESP32 alone:** complete section 1 on the laptop, section 2 for ESP32
only, then run just the ESP32 command in section 4. Neither Pi nor RP2040 is needed
for that first run. After it passes, repeat section 2/4 for RP2040, then section
3/4 for Pi, and finally section 5 with all three powered.

The code uploaded to **both microcontrollers** is `probe/probe.ino`. Make separate
local copies, changing the node ID, chosen GPIO and Wi-Fi credentials for each.
The Pi instead **runs** `linux_probe.py`; do not upload an Arduino sketch to it.

## 1. Record the tested software and equipment

Copy [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md) to `hardware-results/REPORT.md` at
the repository root. Fill in exact board model, OS/core/library versions, Wi-Fi
router/band/distance, power supply, GPIO choices and room conditions.

From the repository root on the laptop:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./openswarm_master-0.2.1-py3-none-any.whl 'openswarm-slave==0.2.0' 'aiohttp>=3.8'
mkdir -p hardware-results
cp benchmarks/hardware/REPORT_TEMPLATE.md hardware-results/REPORT.md
python -m unittest discover -s tests -t . -v > hardware-results/software-tests.log 2>&1
git rev-parse HEAD > hardware-results/revision.txt
git status --short > hardware-results/worktree.txt
git diff > hardware-results/source-changes.patch
python benchmarks/run_benchmarks.py --output-dir hardware-results/software-baseline
```

Copy the prepared master wheel into the current directory first; after its release
it can instead be installed with `pip install openswarm-master==0.2.1`.
The slave registry installation requires its [release](../../docs/releases.md).
The repository is still used for experiment scripts,
tests and the software-only benchmark; it need not be installed as editable software.
The live hardware scripts import the installed packages. Record their `__version__`
and `__file__` as shown in the release guide to verify the actual installation.

An uncommitted working tree can contain the fix even though its HEAD is older.
Preserve the source snapshot actually tested, including new files. Do not identify
the firmware only by its version: unpublished source changes can share that version.
Keep Wi-Fi passwords out of the report, patch and returned source snapshot.

## 2. Install and flash the current Arduino source

After publication, install SwarmNode **0.4.3** from Arduino Library Manager or use
the exact PlatformIO dependency `raihann/SwarmNode@0.4.3`. Confirm the resolved version
in the build output. If the new version is not indexed yet, the source fallback is:
use `slaves/arduino/SwarmNode` from this checkout. In Arduino IDE, remove/rename conflicting installed copies,
then copy this folder into your sketchbook `libraries/SwarmNode` folder. Restart
the IDE. Enable verbose compilation and confirm which SwarmNode path is used.
Keep that verbose build log in the report package.

Copy the `probe/` sketch folder to your own sketchbook. In the copy:

1. Set `PROBE_PIN` to an unused output-capable GPIO for the **exact board**. The
   intentional compile error prevents accidentally using an unspecified pin.
   Record GPIO number and physical header position separately. Use an onboard LED
   if its pin is known, or an external LED with an appropriate series resistor.
2. Set Wi-Fi credentials locally. Use node ID `probe_esp32` on ESP32 and
   `probe_rp2040` on the supported RP2040 Wi-Fi board.
3. Select the correct board/core and USB port; compile/upload. Save the reported
   flash/static-RAM totals and verbose logs. Record the IP address from serial
   output or the router's device list. Check that the output starts LOW.
4. Repeat for the second board. Retain a sanitized sketch with credentials removed.

Keep robot motor/servo power disconnected during these fixture tests. Passing a
GPIO fixture does not validate any motor driver, servo release or loaded arm.

## 3. Prepare the Raspberry Pi probe

Copy the same repository revision/source changes to the Pi. From its repository root:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install 'openswarm-slave[hardware]==0.2.0'
python benchmarks/hardware/linux_probe.py --pin YOUR_FREE_GPIO
```

Replace `YOUR_FREE_GPIO` with a verified GPIO line number, not the header position.
The script uses the existing HAL backend and refuses to run if it falls back to
simulation. Save the printed backend and platform information. Install the backend
dependencies/access permissions appropriate to your Pi OS if real GPIO is unavailable;
do not count a laptop/simulation fallback as physical Pi evidence.

Leave this process running. Stop the usual Pi slave application so UDP port 4210
is free. Allow LAN UDP commands to 4210 and replies to the laptop's source port.
No internet connection is needed for the measurements after dependencies are installed.

## 4. Run the seven functional/timing tests on each board

From the laptop repository root, substitute each board's actual IP:

```bash
python benchmarks/hardware/validate_node.py --ip ESP32_IP --output hardware-results/esp32-run01.json
python benchmarks/hardware/validate_node.py --ip RP2040_IP --output hardware-results/rp2040-run01.json
python benchmarks/hardware/validate_node.py --ip RPI_IP --output hardware-results/rpi-run01.json
```

Each command takes roughly fifteen seconds on a responsive LAN. It sends small JSON
commands to the harmless `probe` actuator and saves timestamped TX/RX packets,
observed STATE data, case outcomes and local source-revision information. A nonzero
exit means at least one FAIL; keep that file. One source endpoint is used for the
whole run; a watchdog epoch reset is explicitly observed between cases. Scheduling
waits maintain transport keepalives, and ACK resets are classified. The runner stops the probe on exit.

| Case | What is tested | Expected observation |
| --- | --- | --- |
| Delayed PING + stale STOP | ACT 10/100, ACT 11/110, PING 9, ACT 10/100; STOP 8; ACT 10 again | ack stays 11, stale ACT never increments acts, STOP zeros value; seq_drop increases twice |
| Wraparound | 32766, PING 32767, ACT 1, old PING/ACT, ACT 2 | old pre-wrap ACT rejected, ack progresses to 2 |
| Scheduled queue | ACT for about 500 ms ahead, old PING/ACT; then another scheduled ACT and stale STOP | first callback occurs at/after target with original value; STOP cancels the next pending callback; delivery retries are recorded |
| Lease + heartbeats | One ACT with lease 150 ms, no further ACT, continuing 5 Hz PING | value goes to zero; lease_exp increases once; hold_ms is measured on the board |
| Longer lease + heartbeats | One ACT with lease 450 ms, continuing 5 Hz PING before expiry | output stops around 450 ms despite intervening PINGs |
| No lease + heartbeats | One ACT without lease, continuing 5 Hz PING | value remains active for the observation (>2 s); this is a censored control trial |
| Transport loss | One ACT, then no commands/heartbeats | watchdog stops it after >500 ms; wd_trips increases once |

The initial campaign used ten runs per board. For the patch regression, use the
bounded **three runs per board** in hardware_rerun.md, with distinct filenames in
a new directory. A timeout/failure is data, not a reason to discard a run.

The runner's PASS is functional. It reports lease/watchdog/schedule excess lateness
without imposing an invented universal deadline budget. For this unloaded fixture,
inspect excess above roughly 20 ms as a concern, retain the run and investigate;
it is not automatically proof of a protocol bug. Use measured service/poll timing
to justify the actual timing budget in the paper. `hold_ms` measures the callback
interval, with the board's clock resolution; it does not independently measure
electrical output transitions or physical deceleration.

## 5. Compare immediate and scheduled operation on all three boards

Keep all three probes powered and the Pi script running. Close `validate_node.py`
before starting this SDK test. On the laptop, replace the three IP placeholders:

```bash
python benchmarks/hardware/sync_trial.py --node probe_esp32=ESP32_IP --node probe_rp2040=RP2040_IP --node probe_rpi=RPI_IP --poses 200 --lead-ms 30 --seed 2027 --output hardware-results/sync-lead30-seed2027.json
```

Each run warms up the real PING-only estimator, sends 200 commands per mode at a
nominal 10 Hz, changes the mode order using the seed, and reports mean/p50/p95/p99
**estimated clock-mapped callback skew**. It also saves per-pose JSONL progressively;
a failed run retains completed poses and writes a failure result. Keep both files.
Never use a partial run as a complete 200-pose result.
The v2 trial freezes pretrial measurement calibration, uses coherent snapshots,
records conditional timing intervals and flags causal-interval violations. It does
not clamp negative point estimates into apparently successful measurements.

Repeat with seeds 2028, 2029, 2030, 2031 (unique output filenames). Repeat at lead
times 10 and 60 ms. Record actual achieved duration/rate and failures. First use
quiet Wi-Fi; then repeat with a declared, repeatable network/CPU load and keep those
conditions separate. Do not label incidental Wi-Fi variation as a specified
Uniform/Gaussian jitter distribution: these scripts do not inject controlled jitter.
Do not claim a measured 40 ms/30 ms horizon boundary from these uncontrolled runs.

**Measurement limit:** the three execution clocks are mapped using OpenSwarm's own
offset estimator. Estimator bias/drift affects the reported skew. This is useful
live-board preliminary evidence, but it cannot independently validate synchronization
accuracy or a sub-millisecond physical bound. LEDs/video show only coarse behavior.
For stronger follow-up evidence, use an independent shared-clock observer, such as
a logic analyzer or a separately calibrated Pi GPIO edge-capture setup; neither is
implemented/calibrated by this kit. Do not connect board outputs together.

## 6. Resource/build evidence and actual actuator checks

For each physical MCU, save board FQBN/core/compiler/library versions, full build
command/log, flash bytes and compiler-reported static RAM. Retain ELF/map files if
available. Those figures describe the **probe firmware** and its configuration;
repeat with the intended application and maximum descriptor occupancy before making
capacity claims. Static RAM excludes peak runtime stack/heap usage. Record peak
runtime usage only if measured by a stated target-specific method; otherwise N/M.

Only after the GPIO tests, test your actual drivers unloaded and separately. For
each configured type (servo, PWM, DAC, motor, stepper, custom), record normal
operation, STOP, lease expiry and transport loss. Record actual hold/release/zero
behavior and any blocking delays. Unsupported/unavailable types are N/T, not PASS.
Raw PIN commands have no per-actuator lease and are not a substitute for this test.
Loaded-arm stopping limits, gravity behavior and motor power faults need a separate
mechanical/electrical validation; the probe's CUSTOM stop callback does not cover them.

## 7. Send back a complete evidence package

Complete [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md). Return it with all per-board JSON
files, sync JSON + JSONL files, compiler logs/maps, sanitized sketches, Pi backend
details, software-baseline results and the exact tested source snapshot/revision.
Include failures, resets, Wi-Fi interruptions and deviations. Optional photos/video
help explain the setup but do not replace timing data. Zip `hardware-results/` and
attach it here; include large source/build files separately if necessary.

The review will check provenance, complete trial counts, stale-packet counters,
lease/watchdog distributions, missing/extra callbacks, clock-estimation assumptions,
and whether each proposed paper claim follows from the measurements. Any unsupported
claim or failed test stays visible in the assessment.

## Arduino publication

Arduino source changed in SwarmNode.cpp/SwarmProtocol.h (alongside the earlier
protocol work). `library.properties` and `library.json` are now **0.4.3**; nothing was published here.
The main-branch workflow tests the repository, synchronizes the standalone SwarmNode
branch and creates `v0.4.3` if that tag does not exist. The workflow deliberately
does not move an existing tag. Let that workflow create the Arduino release tree;
do not create a main-repository tag as a substitute for the standalone library tree.
