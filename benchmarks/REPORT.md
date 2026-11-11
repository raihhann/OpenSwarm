# OpenSwarm: Reproducible Preliminary Software Validation

This report contains **host measurements and deterministic simulations**, not physical Wi-Fi, MCU execution, or robot-motion measurements. No external network access, live sockets, hardware, or third-party Python packages are required.

- Seed: `2027`; parser commands/profile: `100,000`.
- Suite runtime: **3.564 s**; target: <10 s; met: **True**.
- Host: `Windows-11-10.0.26300-SP0`; Python `3.14.7`; machine `AMD64`.
- C++ compiler: `g++.EXE (Rev4, Built by MSYS2 project) 16.2.0`.
- Logical-result fingerprint: `558143c3b557703e0158c7de203afa4697cd192c19cc7aa02b6153416356e5d6`.
- Source SHA-256 hashes, workload details, raw synchronization skews, compiler flags and measurements are in `results.json`.

## Interpretation and reproducibility

The seed, event ordering and logical outcomes are reproducible. Host parser latency, CPU measurements and processing percentiles vary with load, compiler and hardware; identical timing numbers are neither expected nor fabricated. Percentiles use linear interpolation at `(n-1)*q`. Warmup/calibration packets are excluded from scaling counts.

Run `python benchmarks/run_benchmarks.py`; optionally choose `--output-dir PATH`. Missing/failed compilers are reported as unavailable rather than replaced by hard-coded performance numbers. The <10 s target was evaluated on the recorded host, not guaranteed on every computer.

## 1. Memory and firmware parser

`g++ -D__AVR__` selects AVR **capacities**, not the AVR ABI. Both host probes include the actual SwarmTypes.h, SwarmProtocol.h and SwarmNode.h. Only Arduino/transport classes are stubbed: WiFiUDP is a one-byte placeholder and IPAddress is four bytes; the hardware HAL is skipped. Consequently host sizeof(SwarmNode) is exact for that stubbed host build and is **not target static RAM**.

### Host sizeof values (bytes; transport-stubbed object)

| Profile | Pointer | Act table | Sens table | Node object | Buffer budget |
| --- | --- | --- | --- | --- | --- |
| avr_8bit | 8 | 576 | 640 | 1288 | 800 |
| mcu_32bit | 8 | 1344 | 1440 | 2856 | 800 |

<details><summary>LaTeX-ready table</summary>

```latex
\begin{table}[t]
\centering
\small
\caption{Host sizeof values (bytes; transport-stubbed object)}
\label{tab:host_memory}
\begin{tabular}{llllll}
\hline
Profile & Pointer & Act table & Sens table & Node object & Buffer budget \\
\hline
avr\_8bit & 8 & 576 & 640 & 1288 & 800 \\
mcu\_32bit & 8 & 1344 & 1440 & 2856 & 800 \\
\hline
\end{tabular}
\end{table}
```

</details>

### Host C++ parser + acceptSeq + scheduleDelayMs microbenchmark

| Profile | Status | Commands | us/cmd | cmd/s | new calls |
| --- | --- | --- | --- | --- | --- |
| avr_8bit | measured | 100000 | 1.024445 | 976138 | 0 |
| mcu_32bit | measured | 100000 | 0.818011 | 1222477 | 0 |

<details><summary>LaTeX-ready table</summary>

```latex
\begin{table}[t]
\centering
\small
\caption{Host C++ parser + acceptSeq + scheduleDelayMs microbenchmark}
\label{tab:host_parser}
\begin{tabular}{llllll}
\hline
Profile & Status & Commands & us/cmd & cmd/s & new calls \\
\hline
avr\_8bit & measured & 100000 & 1.024445 & 976138 & 0 \\
mcu\_32bit & measured & 100000 & 0.818011 & 1222477 & 0 \\
\hline
\end{tabular}
\end{table}
```

</details>

The timed loop parses six fields from a prebuilt corpus with varying angles, timestamps and sequence numbers, and exercises sequence acceptance/wraparound and scheduling arithmetic. Corpus preparation is excluded from timing and the embedded memory budget. A volatile checksum prevents dead-code removal. The C++ new/new[] counter covers that hot loop; it does not intercept C malloc or prove the whole firmware allocation-free. No embedded execution-speed claim follows from host timings.

The 160-byte RX, 256-byte HELLO TX and 384-byte STATE TX arrays sum to **800 bytes**. These are function-local buffers, not persistent class fields. Their sum is a conservative component budget, not a measured simultaneous peak stack usage.

### Target descriptor layout projections (optionally checked by cross-compiler object symbols)

| Profile | Act desc B | Sens desc B | Act table B | Sens table B | Target check |
| --- | --- | --- | --- | --- | --- |
| avr_8bit | 82 | 61 | 492 | 488 | measured_from_target_object |
| mcu_32bit | 88 | 72 | 1232 | 1296 | measured_from_target_object |

<details><summary>LaTeX-ready table</summary>

```latex
\begin{table}[t]
\centering
\small
\caption{Target descriptor layout projections (optionally checked by cross-compiler object symbols)}
\label{tab:target_descriptors}
\begin{tabular}{llllll}
\hline
Profile & Act desc B & Sens desc B & Act table B & Sens table B & Target check \\
\hline
avr\_8bit & 82 & 61 & 492 & 488 & measured\_from\_target\_object \\
mcu\_32bit & 88 & 72 & 1232 & 1296 & measured\_from\_target\_object \\
\hline
\end{tabular}
\end{table}
```

</details>

Projection assumptions: AVR uses 2-byte function pointers/alignment 1; the generic ILP32 model uses 4-byte pointers/alignment up to 4; float is four bytes and bool one. Optional avr-g++ and arm-none-eabi-g++ probes compile the actual descriptors and read sizes from target object symbols, without running MCU code. An ARM object check does not validate the ESP32 ABI.

**Full target sizeof(SwarmNode) and total firmware RAM are unavailable in this suite.** The board budget below includes descriptor tables and known scalar/array member payloads plus the 800-byte buffer allowance. It excludes `_udp`, `_masterIP`, class inter-member padding, board/core/library globals, heap, other stack frames and RTOS task stacks. Thus it is a partial estimate, not evidence that a complete firmware image fits on a particular board.

### Board SRAM budgets (partial projections; 24 KiB reference is unmeasured)

| Board | SRAM B | Known budget B | Partial % | Full target B | 24 KiB ref % |
| --- | --- | --- | --- | --- | --- |
| UNO WiFi Rev2 | 6144 | 1833 | 29.834 | N/A | 400.000 |
| Nano 33 IoT | 32768 | 3381 | 10.318 | N/A | 75.000 |
| UNO R4 WiFi | 32768 | 3381 | 10.318 | N/A | 75.000 |
| RP2040 | 270336 | 3381 | 1.251 | N/A | 9.091 |
| ESP32 (classic) | 532480 | 3381 | 0.635 | N/A | 4.615 |

<details><summary>LaTeX-ready table</summary>

```latex
\begin{table}[t]
\centering
\small
\caption{Board SRAM budgets (partial projections; 24 KiB reference is unmeasured)}
\label{tab:sram_budget}
\begin{tabular}{llllll}
\hline
Board & SRAM B & Known budget B & Partial \% & Full target B & 24 KiB ref \% \\
\hline
UNO WiFi Rev2 & 6144 & 1833 & 29.834 & N/A & 400.000 \\
Nano 33 IoT & 32768 & 3381 & 10.318 & N/A & 75.000 \\
UNO R4 WiFi & 32768 & 3381 & 10.318 & N/A & 75.000 \\
RP2040 & 270336 & 3381 & 1.251 & N/A & 9.091 \\
ESP32 (classic) & 532480 & 3381 & 0.635 & N/A & 4.615 \\
\hline
\end{tabular}
\end{table}
```

</details>

Board SRAM values are nominal chip totals from the requested benchmark specification, not measurements of memory available to an application. The requested ~24 KiB micro-ROS number is retained solely as an illustrative reference. It is **not a universal minimum**, a measured baseline or a compatibility test. micro-ROS memory depends on configuration, entities, transport, histories, and stack/dynamic memory; see its [official memory profiling methodology](https://micro.vulcanexus.org/docs/concepts/benchmarking/memo_prof/). Do not claim a measured micro-ROS memory improvement from this table.

## 2. HydraArm synchronization under injected delay

200 poses per case; four actuator commands across three role-labeled Linux node instances with distinct boot offsets. Both modes use the same seeded delay trace. Calibration uses real SDK PING/STATE estimation, not assigned perfect offsets. One-way arrival delay is 3 ms + Uniform(0, spread); lead is 30 ms.

The benchmark feeds actual SDK packets into the actual Linux command parser and one-slot pending queues, runs due-command polling, and records callback execution times. Board labels do not emulate ESP32/RP2040/RPi instruction timing. The 1/1/1 ms poll case is idealized; 2/2/10 ms is a heterogeneous polling assumption. Both exclude clock drift, actuator motion, thread scheduling and physical Wi-Fi. No sub-millisecond physical synchronization guarantee is established.

### Simulated inter-controller callback skew (ms), late commands (%)

| Polling model | Spread ms | Mode | Mean | p50 | p95 | p99 | Late % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| idealized_1ms | 5 | baseline | 2.436 | 2.475 | 4.436 | 4.681 | N/A |
| idealized_1ms | 5 | scheduled | 0.385 | 0.000 | 1.000 | 1.000 | 0.000 |
| idealized_1ms | 15 | baseline | 7.802 | 7.994 | 13.249 | 14.216 | N/A |
| idealized_1ms | 15 | scheduled | 0.145 | 0.000 | 1.000 | 1.000 | 0.000 |
| idealized_1ms | 25 | baseline | 12.068 | 11.295 | 21.206 | 24.126 | N/A |
| idealized_1ms | 25 | scheduled | 0.280 | 0.000 | 1.000 | 1.000 | 0.000 |
| idealized_1ms | 40 | baseline | 19.635 | 19.212 | 33.500 | 38.038 | N/A |
| idealized_1ms | 40 | scheduled | 3.756 | 1.932 | 11.132 | 11.809 | 26.750 |
| heterogeneous_polling | 5 | baseline | 2.436 | 2.475 | 4.436 | 4.681 | N/A |
| heterogeneous_polling | 5 | scheduled | 8.000 | 8.000 | 8.000 | 8.000 | 0.000 |
| heterogeneous_polling | 15 | baseline | 7.802 | 7.994 | 13.249 | 14.216 | N/A |
| heterogeneous_polling | 15 | scheduled | 8.000 | 8.000 | 8.000 | 8.000 | 0.000 |
| heterogeneous_polling | 25 | baseline | 12.068 | 11.295 | 21.206 | 24.126 | N/A |
| heterogeneous_polling | 25 | scheduled | 8.000 | 8.000 | 8.000 | 8.000 | 0.000 |
| heterogeneous_polling | 40 | baseline | 19.635 | 19.212 | 33.500 | 38.038 | N/A |
| heterogeneous_polling | 40 | scheduled | 7.532 | 8.000 | 10.039 | 10.762 | 26.750 |

<details><summary>LaTeX-ready table</summary>

```latex
\begin{table}[t]
\centering
\small
\caption{Simulated inter-controller callback skew (ms), late commands (\%)}
\label{tab:sim_sync}
\begin{tabular}{llllllll}
\hline
Polling model & Spread ms & Mode & Mean & p50 & p95 & p99 & Late \% \\
\hline
idealized\_1ms & 5 & baseline & 2.436 & 2.475 & 4.436 & 4.681 & N/A \\
idealized\_1ms & 5 & scheduled & 0.385 & 0.000 & 1.000 & 1.000 & 0.000 \\
idealized\_1ms & 15 & baseline & 7.802 & 7.994 & 13.249 & 14.216 & N/A \\
idealized\_1ms & 15 & scheduled & 0.145 & 0.000 & 1.000 & 1.000 & 0.000 \\
idealized\_1ms & 25 & baseline & 12.068 & 11.295 & 21.206 & 24.126 & N/A \\
idealized\_1ms & 25 & scheduled & 0.280 & 0.000 & 1.000 & 1.000 & 0.000 \\
idealized\_1ms & 40 & baseline & 19.635 & 19.212 & 33.500 & 38.038 & N/A \\
idealized\_1ms & 40 & scheduled & 3.756 & 1.932 & 11.132 & 11.809 & 26.750 \\
heterogeneous\_polling & 5 & baseline & 2.436 & 2.475 & 4.436 & 4.681 & N/A \\
heterogeneous\_polling & 5 & scheduled & 8.000 & 8.000 & 8.000 & 8.000 & 0.000 \\
heterogeneous\_polling & 15 & baseline & 7.802 & 7.994 & 13.249 & 14.216 & N/A \\
heterogeneous\_polling & 15 & scheduled & 8.000 & 8.000 & 8.000 & 8.000 & 0.000 \\
heterogeneous\_polling & 25 & baseline & 12.068 & 11.295 & 21.206 & 24.126 & N/A \\
heterogeneous\_polling & 25 & scheduled & 8.000 & 8.000 & 8.000 & 8.000 & 0.000 \\
heterogeneous\_polling & 40 & baseline & 19.635 & 19.212 & 33.500 & 38.038 & N/A \\
heterogeneous\_polling & 40 & scheduled & 7.532 & 8.000 & 10.039 & 10.762 & 26.750 \\
\hline
\end{tabular}
\end{table}
```

</details>

At spread 40 ms, arrival delays reach **43 ms**, beyond the 30 ms lead. The node executes already-late commands immediately; the table reports the observed failure boundary rather than excluding late samples. Timestamp quantization, clock-estimation bias and polling remain even when every packet arrives before its deadline. One-slot replacement is unchanged; sync_actuate now rejects unknown/expired clocks instead of silently sending an unscheduled command.

## 3. Master-mediated scaling

Actual SDK dispatch/serialization and receive/drain/state-update paths; no OS UDP, sockets, threads, congestion or physical Wi-Fi. RX latency is host processing time, not network latency. CPU includes measurement-call overhead; service rate includes harness work and is not maximum wire capacity.

Each node receives 20 ACT/s and produces 20 scheduled STATE/s, plus 5 PING/s and 5 immediate PING-response STATE/s. Total delivered rate is therefore 50N packets/s; the primary ACT/STATE workload alone is 40N. Rates use simulated time; in-process service rate uses host wall time and is not a measured sustainable Wi-Fi rate. Foreground methods are exercised with background threads disabled.

### Host master RX processing (ms), simulated offset error/rate, projected CPU

| N | RX p50 | RX p95 | RX p99 | Offset MAE ms | Delivered pkt/s | CPU % |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.026900 | 0.034285 | 0.039266 | 0.500 | 50 | 0.000 |
| 5 | 0.025400 | 0.044990 | 0.205332 | 0.500 | 250 | 0.781 |
| 10 | 0.023650 | 0.046815 | 0.075679 | 0.500 | 500 | 1.562 |
| 20 | 0.020400 | 0.036405 | 0.081621 | 0.500 | 1000 | 1.562 |
| 50 | 0.019000 | 0.035410 | 0.067712 | 0.500 | 2500 | 5.469 |

<details><summary>LaTeX-ready table</summary>

```latex
\begin{table}[t]
\centering
\small
\caption{Host master RX processing (ms), simulated offset error/rate, projected CPU}
\label{tab:scale_processing}
\begin{tabular}{lllllll}
\hline
N & RX p50 & RX p95 & RX p99 & Offset MAE ms & Delivered pkt/s & CPU \% \\
\hline
1 & 0.026900 & 0.034285 & 0.039266 & 0.500 & 50 & 0.000 \\
5 & 0.025400 & 0.044990 & 0.205332 & 0.500 & 250 & 0.781 \\
10 & 0.023650 & 0.046815 & 0.075679 & 0.500 & 500 & 1.562 \\
20 & 0.020400 & 0.036405 & 0.081621 & 0.500 & 1000 & 1.562 \\
50 & 0.019000 & 0.035410 & 0.067712 & 0.500 & 2500 & 5.469 \\
\hline
\end{tabular}
\end{table}
```

</details>

### Modeled ACK RTT (ms) and host in-process service rate

| N | RTT p50 | RTT p95 | RTT p99 | Service pkt/s |
| --- | --- | --- | --- | --- |
| 1 | 8.000 | 8.000 | 8.000 | 25278 |
| 5 | 8.000 | 8.000 | 8.000 | 24527 |
| 10 | 8.000 | 8.000 | 8.000 | 26117 |
| 20 | 8.000 | 8.000 | 8.000 | 31116 |
| 50 | 8.000 | 8.000 | 8.000 | 33027 |

<details><summary>LaTeX-ready table</summary>

```latex
\begin{table}[t]
\centering
\small
\caption{Modeled ACK RTT (ms) and host in-process service rate}
\label{tab:scale_rtt}
\begin{tabular}{lllll}
\hline
N & RTT p50 & RTT p95 & RTT p99 & Service pkt/s \\
\hline
1 & 8.000 & 8.000 & 8.000 & 25278 \\
5 & 8.000 & 8.000 & 8.000 & 24527 \\
10 & 8.000 & 8.000 & 8.000 & 26117 \\
20 & 8.000 & 8.000 & 8.000 & 31116 \\
50 & 8.000 & 8.000 & 8.000 & 33027 \\
\hline
\end{tabular}
\end{table}
```

</details>

RTT includes the modeled telemetry response wait as well as forward/reverse transport delay. The current ack tracks received sequence state, not proof that a scheduled actuator has executed. Clock calibration now uses PING-only samples, selects the lowest-delay sample in a five-second window, includes 1 ms quantization in its conditional send/receive bounds, and exposes age/drift assumptions through coherent snapshots. Ordinary ACT ACKs no longer recalibrate the clock; asymmetric delays and drift still limit accuracy. Host processing percentiles must not be cited as network RTT. CPU is measured around master dispatch and receive operations and projected onto the simulated workload period, not an OS CPU-utilization survey.

## 4. Sequence rejection, packet loss, and stalled application

Reordering trial re-inserts older packets after newer packets; 15% is relative to primary commands, not all delivered packets. Deadlock stops application sends while keepalives continue. No-lease stop time is right-censored, not proof of infinite energization. Logical callback stops do not establish physical stopping time or emergency-stop coverage on every driver.

### 200 primary trajectory commands (0 to 180 degrees), 30 stale insertions

| Mode | Delivered | Stale | Applied | Inversions | seq_drop |
| --- | --- | --- | --- | --- | --- |
| No seq | 230 | 30 | 230 | 30 | 0 |
| With seq | 230 | 30 | 200 | 0 | 30 |

<details><summary>LaTeX-ready table</summary>

```latex
\begin{table}[t]
\centering
\small
\caption{200 primary trajectory commands (0 to 180 degrees), 30 stale insertions}
\label{tab:sequence_fault}
\begin{tabular}{llllll}
\hline
Mode & Delivered & Stale & Applied & Inversions & seq\_drop \\
\hline
No seq & 230 & 30 & 230 & 30 & 0 \\
With seq & 230 & 30 & 200 & 0 & 30 \\
\hline
\end{tabular}
\end{table}
```

</details>

Protected stale rejection: **100.0%**. Injection is 15% of primary commands (13.04% of delivered packets). In a separate seeded 15% primary-command loss trial, 170 commands were applied with 0 inversions. There is no retransmission/reliability claim.

**Adversarial control/data regression (fixed):** ACT(seq=10, angle=100), ACT(seq=11, angle=110), delayed PING(seq=9), stale ACT(seq=10, angle=100) produced **0 backward inversion(s)**, seq_drop=1, and final angle=110. The benchmark fails if this regression recurs. PING and STOP only advance the sequence watermark when newer; stale PING still receives STATE and stale STOP still stops outputs. Arduino runtime and Python handler regressions additionally cover STOP and wraparound. Ordering assumes one unchanged session, sequenced commands, and less than half a sequence cycle of separation; endpoint/watchdog resets and legacy unsequenced commands remain outside that guarantee.

### Actual Linux node loop with a simulated 1 ms poll: time to logical stop

| Case | PING Hz | Stop ms | lease_exp | wd_trips | Energized at end |
| --- | --- | --- | --- | --- | --- |
| transport_only | 5 | >2500 (censored) | 0 | 0 | True |
| lease_150ms | 5 | 150.000 | 1 | 0 | False |
| total_transport_loss | 0 | 501.000 | 0 | 1 | False |

<details><summary>LaTeX-ready table</summary>

```latex
\begin{table}[t]
\centering
\small
\caption{Actual Linux node loop with a simulated 1 ms poll: time to logical stop}
\label{tab:deadlock_fault}
\begin{tabular}{llllll}
\hline
Case & PING Hz & Stop ms & lease\_exp & wd\_trips & Energized at end \\
\hline
transport\_only & 5 & >2500 (censored) & 0 & 0 & True \\
lease\_150ms & 5 & 150.000 & 1 & 0 & False \\
total\_transport\_loss & 0 & 501.000 & 0 & 1 & False \\
\hline
\end{tabular}
\end{table}
```

</details>

The application sends one command and then no more. Background PING continues in the two deadlock cases. The actual Linux _background_loop performs both watchdog and lease polling. The third case removes all further transport traffic. These are logical stop callbacks, not motor current/shaft measurements or proof of independent hardware safety.

## Paper claim boundaries and next validation

Supported here: reproducible logical behavior under declared injected delays/faults; host parsing and SDK processing costs; descriptor-layout measurements/projections with explicit ABI scope; failure once the scheduling lead is exceeded.

Still required: actual board builds and linker maps for total RAM/flash; stack high-water marks; calibrated GPIO/logic-analyzer measurements across physical controllers; clock drift and asymmetric Wi-Fi delays; concurrent-thread contention; sustainable network scaling; queue replacement and reconnect/sequence-reset stress tests; and matched micro-ROS/Klipper-style baselines before claiming comparative novelty or superiority.

Research framing and submission requirements are separate from these engineering checks. The [RSS 2027 call for papers](https://roboticsconference.org/information/cfp/) asks for a fully developed problem, hypotheses and methodology at Stage 1; these preliminary software results alone do not establish novelty or acceptance readiness.
