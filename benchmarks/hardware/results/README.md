# Saved hardware campaigns

Raw observations belong beside the hardware-validation tools rather than in the
repository root. This reorganization preserves the contents of all saved files.

| Directory | Previous location | Contents |
| --- | --- | --- |
| `campaign-01/` | `0.1_hardware-result/` | Earlier ten-runs-per-board campaign and synchronization attempt. |
| `campaign-02/` | `hardware-result/` | Three-runs-per-board campaign, RP2040 `_new` reruns, synchronization sessions, and review files. |
| `local/` | New local output | Ignored workspace for future runs. Not committed automatically. |

The campaigns contain both successes and failures. A directory name is not a pass
label. In campaign-02, the RP2040 `_new` files are the later usable runner results;
the older RP2040 files remain evidence of interrupted checks. Keep these distinct.

Archived REVIEW files retain the original paths and conclusions from when they
were generated. Do not edit raw records or replace an old trial with a new one.
Commands in older documents that refer to root result folders predate this move.

For a new run, from the repository root:

```bash
mkdir -p benchmarks/hardware/results/local/run-01
python benchmarks/hardware/validate_node.py --ip ESP32_IP --output benchmarks/hardware/results/local/run-01/esp32-run01.json
python benchmarks/hardware/analyze_results.py --input benchmarks/hardware/results/local/run-01
```

See [the hardware guide](../README.md) for the complete procedure. The analyzer
writes REVIEW files into its input directory; use a copy of an archived campaign
under `local/` if you want to regenerate a review without changing the archive.
Promote a selected campaign into a new named directory through a reviewed change,
including its setup/provenance report. Do not commit an entire virtual environment.
