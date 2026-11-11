# Review of results marked _new

Scope: three RP2040 board runs and the lead-60-ms/seed-2028 synchronization
attempt, including its partial JSONL. Earlier files are not pooled into these
counts. Raw files remain unchanged; REVIEW_NEW.json records their SHA-256 hashes.

## RP2040: 20 passing cases, one startup timeout

- run01: 7/7 PASS.
- run02: 7/7 PASS.
- run03: 6/7 PASS. The delayed-PING case failed in its reset/setup phase.

The failed phase contains only STOP and PING transmissions, followed by cleanup
STOP about 1007 ms later. There is no received STATE and no ACT transmission in
that case. This is a startup/response timeout, not observed incorrect actuation,
lease failure, stale-command acceptance or another false ACK-reset alarm.
The record does not establish whether the command, reply or host observation was
lost/delayed. The following six cases in the same run completed successfully.

Across the three new runs, scheduling/cancellation, sequence wraparound, both
lease tests, the no-lease control and transport-loss tests each passed 3/3. The
150-ms lease measured 152 ms in all three; the 450-ms lease measured 451, 453 and
450 ms. Scheduled callback lateness was 3 ms in all three. These are local CUSTOM
probe callback measurements, not independent physical-edge measurements.

## A separate synchronization attempt failed on ESP32

The lead-60-ms/seed-2028 trial saved all 200 immediate-mode poses and 130
scheduled-mode poses (indices 0..129), then timed out at scheduled pose index 130.
Retain the attempt as FAIL; the 330 saved poses do not form a complete 400-pose run.

| Node | Expected callback count | Observed count | Observed value | Result at failed pose |
| --- | --- | --- | --- | --- |
| ESP32 | 2871 | 2870 | 130 | One execution behind |
| RP2040 | 2911 | 2911 | 131 | Executed requested pose value |
| Pi | 2471 | 2471 | 131 | Executed requested pose value |

At timeout all three still reported ack 517, and their watchdog and stale-drop
counters had not changed from the previous saved pose. The ESP32 was therefore
still communicating, but its expected callback was not observed. A cumulative
receive ACK/heartbeat is not an execution receipt. Command loss is consistent
with this trace, but there is no per-ACT packet capture/execution receipt proving
where the command was lost or not applied. No watchdog stop or clock reset is
reported at the failed pose.

Saved poses have zero recorded causal-interval violations. That does not turn
the incomplete session into a pass or establish independent physical skew.

## Severity and whether this can be future work

The isolated RP2040 startup timeout can be disclosed as a transport/connection
availability limitation if the framework is explicitly scoped to best-effort
UDP, with failures surfaced to the application. It does not demonstrate a new
actuator-safety defect. It still counts in attempted-trial reliability.

The synchronization failure is relevant to the central coordinated-execution
claim: one controller can retain its old target while others execute a new pose.
Current data do not support guaranteed synchronized completion, confirmed command
delivery, or robust closed-loop multi-joint operation under loss. A paper can
report this failure and scope conclusions to received commands/declared conditions;
reliable delivery/execution confirmation may then be clearly stated future work.
It cannot be omitted or described as a passed synchronization trial.

For a stronger operational guarantee, define and implement a policy for detecting
missing application/execution acknowledgements and aborting/stopping or safely
retrying within a deadline. Retrying raw relative-motion commands without an
idempotency/deadline contract is not a general fix. This is a separate design
decision from increasing an observer timeout until a test happens to pass.

No software, firmware, package versions or release tags were changed for this
review. No additional full hardware campaign is requested by this report.
