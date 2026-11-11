# OpenSwarm: RSS 2027 Stage 1 evidence and readiness

This is an engineering and research assessment, not a claim of acceptance readiness.
The current implementation supports a scoped methodology and preliminary software
results. Research novelty, complete board resource measurements, and physical timing
remain open. Adding features alone does not establish a publishable contribution.

The [official RSS 2027 call](https://roboticsconference.org/information/cfp/), checked
November 11, 2026, requires a fully developed problem, hypotheses and methodology.
Experiments may be preliminary. Stage 1 is due December 4, 2026 (AoE), with up to
five content pages and one references page. The paper must contain its evidence;
websites/appendices are not reviewed, and external links are prohibited in the
blinded submission. This repository document is an internal preparation artifact.

## Proposed scope and research question

Can a small, master-mediated execution layer coordinate heterogeneous controllers
with useful timing consistency under bounded network delay, while exposing the
resource cost and failure boundaries on resource-constrained boards?

The implemented architecture is a Python coordinator plus Arduino/Linux slaves,
with sequenced UDP commands, clock-offset estimates, one pending command per
actuator, and optional command leases. Small Wi-Fi controllers can provide useful
local I/O without a full robotics middleware stack on each board. That motivation
must not become a blanket claim that low-cost controllers cannot run ROS-related
software: supported boards and middleware configurations vary.

HydraArm supplies a heterogeneous controller workload. Two robots or a swarm
cooperating on shared tasks is the longer-term application vision. Today commands
are mediated by the master; peer-to-peer coordination, distributed consensus,
multi-robot planning, and decentralized fault tolerance are not implemented claims.

## Implemented contracts and present evidence

| Contract | Evidence | Limit |
| --- | --- | --- |
| Delayed PING cannot reopen stale ACT/PIN acceptance | Original counterexample is now a benchmark failure gate; Arduino runtime and Linux/virtual handler regressions | Unchanged sender session, sequenced packets, separation below half a cycle |
| Stale STOP remains effective without rewinding ordering | Runtime/handler tests, including cancellation of pending commands | Logical callbacks/output requests; no independent hardware safety guarantee |
| Wraparound preserves ordering | Tests for 32767 to 1, stale pre-wrap traffic, half-window boundary | No ordering across endpoint/watchdog session resets or legacy unsequenced commands |
| Scheduled dispatch can reduce arrival-induced skew | Seeded 200-pose comparisons using actual SDK/Linux command paths | Declared clocks, delays and polling; no physical MCU/Wi-Fi measurement |
| Leases stop commands despite transport heartbeats | Real Linux loop under simulated time, 150 ms lease, continuing 5 Hz PING | Runtime stalls/blocking drivers can delay enforcement; physical stop unmeasured |
| Costs are reproducible and auditable | Host C++ parser, descriptor probes, source hashes, raw JSON, generated tables | Host ABI is not target ABI; full target RAM/stack not measured |

The normative sequence and scheduling definitions are in [protocol.md](protocol.md).
`ack` is a receive watermark, not an execution receipt. Sequence values cycle over
1..32767; only forward modular distances 1..16383 advance ordering. PING/STOP never
reset ordering. A changed endpoint or watchdog recovery starts a new session.
Delayed packets across those boundaries can still be accepted; stronger session
identities and ownership remain deferred, so experiments must distinguish these cases.

## Falsifiable hypotheses and planned comparisons

1. **Timing:** within the lead-time horizon, scheduled dispatch reduces skew
   relative to immediate dispatch under otherwise identical delay samples.
   Compare paired per-pose outcomes, mean/p50/p95/p99, late-arrival counts and
   deadline misses. Sweep delay spread, asymmetry, clock drift, lead time and poll
   periods. A negative result identifies where clock/poll error dominates jitter.
2. **Resource cost:** bounded descriptor/queue state and allocation-free parsing
   offer a useful execution layer on constrained targets. Establish this with
   actual board builds, linker maps, stack high-water marks, and matched workloads.
   Descriptor arithmetic alone does not prove that a complete firmware fits 6 KiB.
3. **Fault behavior:** within a session, stale command rejection prevents the
   tested trajectory regressions; application leases expire despite heartbeats.
   Measure both software callbacks and physical outputs. Exercise repeated faults,
   late commands, queue replacement, endpoint changes, reboot and reconnection.

For an explicit conditional timing model, write execution as `t_i = T + e_i + u_i`.
If all packets arrive before the mapped deadline, total clock/mapping/quantization
error satisfies `|e_i| <= E`, and service delay satisfies `0 <= u_i <= Q`, then
pairwise software execution skew is at most `2E + Q`. This is an algebraic bound
under stated assumptions, not a measured framework guarantee. Blocking operations,
unbounded drift, late arrival or queue replacement invalidate those assumptions.
The current fallback executes late/out-of-horizon commands immediately.

## Submission gates still open

- **Central contribution and related work:** compare the mechanism and scope
  directly with relevant clock-scheduled controller systems (including Klipper),
  constrained robotics middleware and multi-controller robot architectures. Use
  verified primary literature. Define the specific insight beyond combining known
  sequence, scheduling and lease mechanisms. Novelty is not established yet.
- **Representative target builds:** compile the actual board/library combinations,
  record toolchain/dependency versions, and retain map files and flash/RAM sizes.
  Host `-D__AVR__` selects capacities, not an AVR ABI or target runtime test.
- **One physical heterogeneous timing experiment:** use a shared logic analyzer
  for GPIO execution markers on ESP32, RP2040 and Linux. Compare paired immediate
  and scheduled trials across delay regimes; separately record servo pulse/shaft
  response. Include clock offset/drift and poll-time measurements.
- **Comparable baselines:** immediate dispatch is implemented. Matched middleware
  or clock-scheduling baselines still need implementation/measurement. The report's
  illustrative 24 KiB micro-ROS reference is not an established minimum and cannot
  support a superiority claim. Report configuration and equivalent functionality.
- **Statistics and reproducibility:** use multiple declared seeds/trials and
  uncertainty estimates for experimental comparisons. The quick seed-2027 suite
  is a regression/preliminary-validation run, not independent repeated evidence.
  Freeze a revision, source fingerprints, commands and raw measurements for paper tables.
- **Real scaling:** measure sustained UDP operation, contention, loss, CPU and
  reconnect behavior on physical hosts/networks. The current N=1,5,10,20,50 test
  measures master processing under a simulated workload, not Wi-Fi capacity.

These gates organize Stage 1 preparation; RSS permits preliminary experiments, so
not every hardware campaign must finish before submission. The method, assumptions,
baseline selection and plan for learning from negative results must be complete.
The highest-value next work is the novelty comparison and one physical timing
experiment, rather than expanding the framework into peer-to-peer swarm control.

## Reproduce the current software evidence

```console
python -m unittest discover -s tests -t . -v
python benchmarks/run_benchmarks.py
```

Use Python 3.8+ and host `g++` for firmware host tests/measurements; optional cross
compilers add descriptor-layout evidence. Compiler absence is reported/skipped,
not replaced by invented timings. No hardware or external network is needed by
the benchmark. The broader tests include local loopback integration.

The generated [report](../benchmarks/REPORT.md) and [raw results](../benchmarks/results.json)
are the authority for current numbers and measurement scope. Logical fingerprints
should match repeated runs; wall-clock/parser/CPU timings naturally vary.

The [hardware validation kit](../benchmarks/hardware/README.md) provides matching
Arduino/Pi probe fixtures, live UDP fault/lease checks, an SDK synchronization
trial and a report template. Its synchronization metric reuses estimated offsets
and must not be presented as independently measured physical skew. Harness tests
use simulated GPIO over loopback; they do not establish any physical-board result.
