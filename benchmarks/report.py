"""Generate Markdown and plain-LaTeX tables from the same recorded values."""


def _number(value, places=3):
    return "N/A" if value is None else (str(value) if isinstance(value, int) else f"{value:.{places}f}")


def _tex(value):
    escapes = {"\\": r"\textbackslash{}", "_": r"\_", "%": r"\%", "&": r"\&",
               "$": r"\$", "#": r"\#", "{": r"\{", "}": r"\}"}
    return "".join(escapes.get(c, c) for c in str(value))


def _table(title, headers, rows, label):
    lines = ["### " + title, "", "| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(map(str, row)) + " |" for row in rows]
    lines += ["", "<details><summary>LaTeX-ready table</summary>", "", "```latex",
              r"\begin{table}[t]", r"\centering", r"\small",
              r"\caption{" + _tex(title) + "}", r"\label{tab:" + label + "}",
              r"\begin{tabular}{" + "l" * len(headers) + "}", r"\hline",
              " & ".join(map(_tex, headers)) + r" \\", r"\hline"]
    lines += [" & ".join(map(_tex, row)) + r" \\" for row in rows]
    lines += [r"\hline", r"\end{tabular}", r"\end{table}", "```", "", "</details>", ""]
    return lines


def generate_report_markdown(result):
    b1 = result["benchmark_1_memory_and_parser"]
    b2 = result["benchmark_2_hydra_sync_under_jitter"]
    b3 = result["benchmark_3_swarm_scaling"]
    b4 = result["benchmark_4_safety_interlocks"]
    lines = ["# OpenSwarm: Reproducible Preliminary Software Validation", "",
        "This report contains **host measurements and deterministic simulations**, not physical Wi-Fi, MCU execution, or robot-motion measurements. No external network access, live sockets, hardware, or third-party Python packages are required.", "",
        f"- Seed: `{result['seed']}`; parser commands/profile: `{b1['iterations']:,}`.",
        f"- Suite runtime: **{result['total_runtime_sec']:.3f} s**; target: <10 s; met: **{result['within_runtime_target']}**.",
        f"- Host: `{result['environment']['platform']}`; Python `{result['environment']['python']}`; machine `{result['environment']['machine']}`.",
        f"- C++ compiler: `{b1.get('compiler_version', 'unavailable')}`.",
        f"- Logical-result fingerprint: `{result['logical_results_sha256']}`.",
        "- Source SHA-256 hashes, workload details, raw synchronization skews, compiler flags and measurements are in `results.json`.", "",
        "## Interpretation and reproducibility", "",
        "The seed, event ordering and logical outcomes are reproducible. Host parser latency, CPU measurements and processing percentiles vary with load, compiler and hardware; identical timing numbers are neither expected nor fabricated. Percentiles use linear interpolation at `(n-1)*q`. Warmup/calibration packets are excluded from scaling counts.", "",
        "Run `python benchmarks/run_benchmarks.py`; optionally choose `--output-dir PATH`. Missing/failed compilers are reported as unavailable rather than replaced by hard-coded performance numbers. The <10 s target was evaluated on the recorded host, not guaranteed on every computer.", "",
        "## 1. Memory and firmware parser", "",
        "`g++ -D__AVR__` selects AVR **capacities**, not the AVR ABI. Both host probes include the actual SwarmTypes.h, SwarmProtocol.h and SwarmNode.h. Only Arduino/transport classes are stubbed: WiFiUDP is a one-byte placeholder and IPAddress is four bytes; the hardware HAL is skipped. Consequently host sizeof(SwarmNode) is exact for that stubbed host build and is **not target static RAM**.", ""]
    memory_rows, parser_rows = [], []
    for name, profile in b1["profiles"].items():
        host = profile.get("host", {})
        memory_rows.append([name, _number(host.get("pointer_bytes")), _number(host.get("actuator_table_bytes")),
            _number(host.get("sensor_table_bytes")), _number(host.get("sizeof_swarmnode_host_stubbed_bytes")), "800"])
        parser_rows.append([name, profile["host_status"], _number(host.get("iterations")),
            _number(host.get("us_per_cmd"), 6), _number(host.get("commands_per_second"), 0),
            _number(host.get("new_calls_in_loop"))])
    lines += _table("Host sizeof values (bytes; transport-stubbed object)",
        ["Profile", "Pointer", "Act table", "Sens table", "Node object", "Buffer budget"], memory_rows, "host_memory")
    lines += _table("Host C++ parser + acceptSeq + scheduleDelayMs microbenchmark",
        ["Profile", "Status", "Commands", "us/cmd", "cmd/s", "new calls"], parser_rows, "host_parser")
    lines += ["The timed loop parses six fields from a prebuilt corpus with varying angles, timestamps and sequence numbers, and exercises sequence acceptance/wraparound and scheduling arithmetic. Corpus preparation is excluded from timing and the embedded memory budget. A volatile checksum prevents dead-code removal. The C++ new/new[] counter covers that hot loop; it does not intercept C malloc or prove the whole firmware allocation-free. No embedded execution-speed claim follows from host timings.", "",
        "The 160-byte RX, 256-byte HELLO TX and 384-byte STATE TX arrays sum to **800 bytes**. These are function-local buffers, not persistent class fields. Their sum is a conservative component budget, not a measured simultaneous peak stack usage.", ""]
    target_rows = []
    for name, profile in b1["profiles"].items():
        projection, cross = profile["target_projection"], profile["cross_compiler"]
        target_rows.append([name, projection["actuator_descriptor_bytes"], projection["sensor_descriptor_bytes"],
            projection["actuator_table_bytes"], projection["sensor_table_bytes"], cross["status"]])
    lines += _table("Target descriptor layout projections (optionally checked by cross-compiler object symbols)",
        ["Profile", "Act desc B", "Sens desc B", "Act table B", "Sens table B", "Target check"], target_rows, "target_descriptors")
    lines += ["Projection assumptions: AVR uses 2-byte function pointers/alignment 1; the generic ILP32 model uses 4-byte pointers/alignment up to 4; float is four bytes and bool one. Optional avr-g++ and arm-none-eabi-g++ probes compile the actual descriptors and read sizes from target object symbols, without running MCU code. An ARM object check does not validate the ESP32 ABI.", "",
        "**Full target sizeof(SwarmNode) and total firmware RAM are unavailable in this suite.** The board budget below includes descriptor tables and known scalar/array member payloads plus the 800-byte buffer allowance. It excludes `_udp`, `_masterIP`, class inter-member padding, board/core/library globals, heap, other stack frames and RTOS task stacks. Thus it is a partial estimate, not evidence that a complete firmware image fits on a particular board.", ""]
    board_rows = [[r["board"], r["sram_bytes"], r["known_component_budget_bytes"],
                   _number(r["partial_sram_pct"]), "N/A", _number(r["micro_ros_reference_pct"])] for r in b1["boards"]]
    lines += _table("Board SRAM budgets (partial projections; 24 KiB reference is unmeasured)",
        ["Board", "SRAM B", "Known budget B", "Partial %", "Full target B", "24 KiB ref %"], board_rows, "sram_budget")
    lines += ["Board SRAM values are nominal chip totals from the requested benchmark specification, not measurements of memory available to an application. The requested ~24 KiB micro-ROS number is retained solely as an illustrative reference. It is **not a universal minimum**, a measured baseline or a compatibility test. micro-ROS memory depends on configuration, entities, transport, histories, and stack/dynamic memory; see its [official memory profiling methodology](https://micro.vulcanexus.org/docs/concepts/benchmarking/memo_prof/). Do not claim a measured micro-ROS memory improvement from this table.", "",
        "## 2. HydraArm synchronization under injected delay", "",
        f"{b2['poses_per_case']} poses per case; four actuator commands across three role-labeled Linux node instances with distinct boot offsets. Both modes use the same seeded delay trace. Calibration uses real SDK PING/STATE estimation, not assigned perfect offsets. One-way arrival delay is 3 ms + Uniform(0, spread); lead is {b2['lead_ms']:.0f} ms.", "",
        "The benchmark feeds actual SDK packets into the actual Linux command parser and one-slot pending queues, runs due-command polling, and records callback execution times. Board labels do not emulate ESP32/RP2040/RPi instruction timing. The 1/1/1 ms poll case is idealized; 2/2/10 ms is a heterogeneous polling assumption. Both exclude clock drift, actuator motion, thread scheduling and physical Wi-Fi. No sub-millisecond physical synchronization guarantee is established.", ""]
    sync_rows = []
    for row in b2["results"]:
        for mode in ("baseline", "scheduled"):
            stats = row[mode]["skew_ms"]
            late = row[mode]["late_commands"]
            sync_rows.append([row["scheduler"], _number(row["jitter_spread_ms"], 0), mode,
                *[_number(stats[p]) for p in ("mean", "p50", "p95", "p99")],
                "N/A" if late is None else _number(100 * late / (b2["poses_per_case"] * 4))])
    lines += _table("Simulated inter-controller callback skew (ms), late commands (%)",
        ["Polling model", "Spread ms", "Mode", "Mean", "p50", "p95", "p99", "Late %"], sync_rows, "sim_sync")
    lines += ["At spread 40 ms, arrival delays reach **43 ms**, beyond the 30 ms lead. The node executes already-late commands immediately; the table reports the observed failure boundary rather than excluding late samples. Timestamp quantization, clock-estimation bias and polling remain even when every packet arrives before its deadline. One-slot replacement is unchanged; sync_actuate now rejects unknown/expired clocks instead of silently sending an unscheduled command.", "",
        "## 3. Master-mediated scaling", "", b3["scope"], "",
        "Each node receives 20 ACT/s and produces 20 scheduled STATE/s, plus 5 PING/s and 5 immediate PING-response STATE/s. Total delivered rate is therefore 50N packets/s; the primary ACT/STATE workload alone is 40N. Rates use simulated time; in-process service rate uses host wall time and is not a measured sustainable Wi-Fi rate. Foreground methods are exercised with background threads disabled.", ""]
    scale_rows, rtt_rows = [], []
    for row in b3["results"]:
        latency, rtt = row["rx_processing_latency_ms"], row["rtt_ms"]
        scale_rows.append([row["nodes"], *[_number(latency[p], 6) for p in ("p50", "p95", "p99")],
            _number(row["clock_offset_error_ms"]["mean"]), _number(row["delivered_packets_per_simulated_second"], 0),
            _number(row["projected_one_core_cpu_pct_at_workload_rate"])])
        rtt_rows.append([row["nodes"], *[_number(rtt[p]) for p in ("p50", "p95", "p99")],
                         _number(row["in_process_service_rate_pps"], 0)])
    lines += _table("Host master RX processing (ms), simulated offset error/rate, projected CPU",
        ["N", "RX p50", "RX p95", "RX p99", "Offset MAE ms", "Delivered pkt/s", "CPU %"], scale_rows, "scale_processing")
    lines += _table("Modeled ACK RTT (ms) and host in-process service rate",
        ["N", "RTT p50", "RTT p95", "RTT p99", "Service pkt/s"], rtt_rows, "scale_rtt")
    lines += ["RTT includes the modeled telemetry response wait as well as forward/reverse transport delay. The current ack tracks received sequence state, not proof that a scheduled actuator has executed. Clock calibration now uses PING-only samples, selects the lowest-delay sample in a five-second window, includes 1 ms quantization in its conditional send/receive bounds, and exposes age/drift assumptions through coherent snapshots. Ordinary ACT ACKs no longer recalibrate the clock; asymmetric delays and drift still limit accuracy. Host processing percentiles must not be cited as network RTT. CPU is measured around master dispatch and receive operations and projected onto the simulated workload period, not an OS CPU-utilization survey.", "",
        "## 4. Sequence rejection, packet loss, and stalled application", "", b4["scope"], ""]
    seq = b4["sequence"]
    rows = [[mode, seq["delivered_packets"], seq["stale_injected"], seq[key]["applied_commands"],
             seq[key]["backward_inversions"], seq[key]["seq_drop"]] for mode, key in (("No seq", "baseline"), ("With seq", "protected"))]
    lines += _table("200 primary trajectory commands (0 to 180 degrees), 30 stale insertions",
        ["Mode", "Delivered", "Stale", "Applied", "Inversions", "seq_drop"], rows, "sequence_fault")
    loss = seq["packet_loss_trial"]
    lines += [f"Protected stale rejection: **{seq['protected']['stale_rejection_pct']:.1f}%**. Injection is 15% of primary commands ({seq['stale_fraction_of_delivered_pct']:.2f}% of delivered packets). In a separate seeded 15% primary-command loss trial, {loss['applied_commands']} commands were applied with {loss['backward_inversions']} inversions. There is no retransmission/reliability claim.", ""]
    control = seq["reordered_control_probe"]
    lines += [f"**Adversarial control/data regression (fixed):** ACT(seq=10, angle=100), ACT(seq=11, angle=110), delayed PING(seq=9), stale ACT(seq=10, angle=100) produced **{control['backward_inversions']} backward inversion(s)**, seq_drop={control['seq_drop']}, and final angle={control['last_angle']}. The benchmark fails if this regression recurs. PING and STOP only advance the sequence watermark when newer; stale PING still receives STATE and stale STOP still stops outputs. Arduino runtime and Python handler regressions additionally cover STOP and wraparound. Ordering assumes one unchanged session, sequenced commands, and less than half a sequence cycle of separation; endpoint/watchdog resets and legacy unsequenced commands remain outside that guarantee.", ""]
    deadlock_rows = []
    for name, row in b4["deadlock"].items():
        stop = ">2500 (censored)" if row["right_censored"] else _number(row["time_to_stop_ms"])
        deadlock_rows.append([name, row["heartbeat_hz"], stop, row["lease_exp"], row["wd_trips"], str(row["still_energized_at_end"])])
    lines += _table("Actual Linux node loop with a simulated 1 ms poll: time to logical stop",
        ["Case", "PING Hz", "Stop ms", "lease_exp", "wd_trips", "Energized at end"], deadlock_rows, "deadlock_fault")
    lines += ["The application sends one command and then no more. Background PING continues in the two deadlock cases. The actual Linux _background_loop performs both watchdog and lease polling. The third case removes all further transport traffic. These are logical stop callbacks, not motor current/shaft measurements or proof of independent hardware safety.", "",
        "## Paper claim boundaries and next validation", "",
        "Supported here: reproducible logical behavior under declared injected delays/faults; host parsing and SDK processing costs; descriptor-layout measurements/projections with explicit ABI scope; failure once the scheduling lead is exceeded.", "",
        "Still required: actual board builds and linker maps for total RAM/flash; stack high-water marks; calibrated GPIO/logic-analyzer measurements across physical controllers; clock drift and asymmetric Wi-Fi delays; concurrent-thread contention; sustainable network scaling; queue replacement and reconnect/sequence-reset stress tests; and matched micro-ROS/Klipper-style baselines before claiming comparative novelty or superiority.", "",
        "Research framing and submission requirements are separate from these engineering checks. The [RSS 2027 call for papers](https://roboticsconference.org/information/cfp/) asks for a fully developed problem, hypotheses and methodology at Stage 1; these preliminary software results alone do not establish novelty or acceptance readiness.", ""]
    return "\n".join(lines)
