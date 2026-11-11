"""Reproducible logical checks plus one end-to-end offline artifact smoke test."""

import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from tests import ROOT
from benchmarks.memory import _work_directory
from benchmarks.run_benchmarks import (
    run_benchmark_2_hydra_sync_under_jitter,
    run_benchmark_3_swarm_scaling,
    run_benchmark_4_safety_interlocks,
)


class BenchmarkTests(unittest.TestCase):
    def test_seeded_simulations_use_no_network_or_sleep(self):
        with patch("socket.socket", side_effect=AssertionError("Real socket opened")), \
             patch("time.sleep", side_effect=AssertionError("Real sleep requested")):
            first = run_benchmark_2_hydra_sync_under_jitter(poses=12, jitter_levels_ms=(5., 40.))
            second = run_benchmark_2_hydra_sync_under_jitter(poses=12, jitter_levels_ms=(5., 40.))
            safety = run_benchmark_4_safety_interlocks()
        self.assertEqual(first, second)
        for case in first["results"]:
            self.assertEqual(case["scheduled"]["skew_ms"]["count"], 12)
            if case["within_lead_horizon"]:
                self.assertEqual(case["scheduled"]["late_commands"], 0)
        seq = safety["sequence"]
        self.assertGreater(seq["baseline"]["backward_inversions"], 0)
        self.assertEqual(seq["protected"]["seq_drop"], seq["stale_injected"])
        self.assertEqual(seq["protected"]["backward_inversions"], 0)
        control = seq["reordered_control_probe"]
        self.assertEqual(control["backward_inversions"], 0)
        self.assertEqual(control["seq_drop"], 1)
        self.assertEqual(control["last_angle"], 110)
        lease = safety["deadlock"]["lease_150ms"]
        self.assertEqual(lease["lease_exp"], 1)
        self.assertGreaterEqual(lease["time_to_stop_ms"], 150)
        self.assertLessEqual(lease["time_to_stop_ms"], 151)
        self.assertTrue(safety["deadlock"]["transport_only"]["right_censored"])
        self.assertEqual(safety["deadlock"]["total_transport_loss"]["wd_trips"], 1)

    def test_scaling_counts_and_clock_estimation(self):
        with patch("socket.socket", side_effect=AssertionError("Real socket opened")):
            result = run_benchmark_3_swarm_scaling(node_counts=(1, 5), ticks_per_scale=8)
        for row in result["results"]:
            self.assertEqual(row["total_packets"], row["nodes"] * 20)
            self.assertEqual(row["delivered_packets_per_simulated_second"], row["nodes"] * 50)
            self.assertLessEqual(row["clock_offset_error_ms"]["mean"], 2)
            self.assertGreaterEqual(row["rx_processing_latency_ms"]["p50"], 0)

    def test_cli_generates_complete_consistent_artifacts(self):
        with _work_directory() as directory:
            proc = subprocess.run([sys.executable, "-B", str(ROOT / "benchmarks/run_benchmarks.py"),
                                   "--output-dir", str(directory)], cwd=ROOT, capture_output=True,
                                  text=True, timeout=20)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            result = json.loads((directory / "results.json").read_text(encoding="utf-8"))
            report = (directory / "REPORT.md").read_text(encoding="utf-8")
            self.assertEqual(result["schema_version"], 1)
            self.assertEqual(result["seed"], 2027)
            self.assertEqual(result["runtime_target_sec"], 10)
            self.assertIn(result["logical_results_sha256"], report)
            self.assertGreaterEqual(report.count(r"\begin{table}"), 8)
            self.assertEqual(report.count("```"), report.count("```latex") * 2)
            for name, capacities in [("avr_8bit", (6, 8)), ("mcu_32bit", (14, 18))]:
                profile = result["benchmark_1_memory_and_parser"]["profiles"][name]
                if profile["host_status"] == "measured":
                    host = profile["host"]
                    self.assertEqual((host["actuators"], host["sensors"]), capacities)
                    self.assertEqual(host["iterations"], 100000)
                    self.assertEqual(host["accepted"], 100000)
                    self.assertEqual(host["new_calls_in_loop"], 0)
                    self.assertGreater(host["us_per_cmd"], 0)
                else:
                    self.assertNotIn("host", profile)
                self.assertIsNone(profile["target_projection"]["target_sizeof_swarmnode_bytes"])
