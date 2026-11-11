"""The evidence audit must detect counter violations rather than trust PASS labels."""
from copy import deepcopy
import unittest

from benchmarks.hardware.analyze_results import mapped_execution, stats, verify_case_evidence, premature_reset_alarm


class HardwareAnalysisTests(unittest.TestCase):
    def test_classifies_aborted_detector_without_calling_hardware_pass(self):
        case = dict(error_kind="unexpected_session_reset", phase="sequence_wraparound")
        def rx(phase, ack, watchdog):
            return dict(direction="rx", phase=phase, packet=dict(type="STATE", ack=ack, wd_trips=watchdog))
        data = dict(packet_log=[rx("sequence_wraparound/reset", 11, 1),
                                rx("sequence_wraparound/reset", None, 2),
                                rx("sequence_wraparound", None, 2)])
        self.assertTrue(premature_reset_alarm(data, case))
        data["packet_log"].insert(2, rx("sequence_wraparound", 32766, 2))
        self.assertFalse(premature_reset_alarm(data, case))

    def trace(self):
        def tx(**packet):
            return dict(direction="tx", packet=packet)
        def rx(acts, drops=0, value=110):
            return dict(direction="rx", packet=dict(type="STATE", ack=11, seq_drop=drops,
                                                    sensors=dict(acts=acts, value=value)))
        return dict(cases=[dict(name="delayed_ping_and_stale_stop", status="PASS")], packet_log=[
            rx(0, value=0), tx(cmd="ACT", seq=10, value=100), rx(1, value=100),
            tx(cmd="ACT", seq=11, value=110), rx(2), tx(cmd="PING", seq=9),
            tx(cmd="ACT", seq=10, value=100), rx(2, drops=1), tx(cmd="STOP", seq=8),
            rx(2, drops=1, value=0), tx(cmd="ACT", seq=10, value=100),
            rx(2, drops=2, value=0), tx(cmd="STOP")])

    def test_detects_extra_callback_despite_pass_label(self):
        trace = self.trace()
        self.assertEqual(verify_case_evidence(trace), [])
        corrupt = deepcopy(trace)
        corrupt["packet_log"][-2]["packet"]["sensors"]["acts"] = 3
        self.assertIn("delayed_ping_and_stale_stop: callback count inconsistent", verify_case_evidence(corrupt))
        corrupt = deepcopy(trace)
        corrupt["packet_log"][-2]["packet"]["seq_drop"] = 1
        # Remove the only observation of drop=2, so the claimed rejection is unverified.
        self.assertIn("delayed_ping_and_stale_stop: stale-drop count inconsistent", verify_case_evidence(corrupt))

    def test_hello_packets_do_not_masquerade_as_sensor_samples(self):
        trace = self.trace()
        trace["packet_log"].insert(3, dict(direction="rx", packet=dict(type="HELLO", sensors=["acts"])))
        self.assertEqual(verify_case_evidence(trace), [])

    def test_clock_mapping_wrap_and_descriptive_percentiles(self):
        self.assertEqual(mapped_execution(dict(uptime_ms=32770, clock_offset_snapshot_ms=100,
                                              sensors=dict(exec_ms=32760))), 32660)
        # A biased clock map can put a callback before dispatch; preserve rather than clamp it.
        self.assertLess(mapped_execution(dict(uptime_ms=10, clock_offset_snapshot_ms=100,
                                             sensors=dict(exec_ms=5))), 0)
        summary = stats([1, 2, 3, 4])
        self.assertEqual(summary["mean"], 2.5)
        self.assertAlmostEqual(summary["p95"], 3.85)
