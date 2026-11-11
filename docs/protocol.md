# OpenSwarm UDP contract, version 1

Packets are UTF-8 JSON objects. Command nodes listen on their advertised UDP port
(normally 4210); HELLO discovery uses 4211. STATE replies return to the source
endpoint of a command. The master routes using the received source IP and advertised
command port, not the HELLO `ip` string. A STATE must match the known node endpoint.
Node IDs are identities claimed by the sender, not authenticated identities.

## Compatibility

The `protocol` field is optional for existing nodes; omitted means version 1.
Python receivers reject explicitly unsupported versions. Existing Arduino receivers
ignore additive fields. There is no version handshake or authenticated session yet.

HELLO fields: `type: "HELLO"`, `node`, `board`, `port`, `actuators` (names), and
`sensors` (names). Optional fields include `protocol`, `capabilities`, `virtual`,
and `max_command_bytes`. Legacy command capacity defaults to 159 UTF-8 bytes.
Linux advertises 1024 bytes; virtual nodes advertise 2048. The Python master rejects
commands exceeding the advertised capacity. An oversized Arduino datagram is discarded.

STATE fields: `type: "STATE"`, `node`, `uptime_ms` (nonnegative integer), `sensors`
(complete sample of numeric values or lists of one to six values), optional `ack`
(integer `1..32767` acknowledging the latest accepted command `seq`), and optional
nonnegative diagnostic counters (`wd_trips`, `lease_exp`, `seq_drop`) included when
non-zero. Nonfinite values are invalid. Linux adds `sensor_errors`, mapping omitted
sensors to error descriptions. A later successful sample clears those errors. A
callback returning an invalid shape or failing does not terminate Linux telemetry
generation.

## Commands

| Command | Fields |
| --- | --- |
| PING | `cmd: "PING"`, optional `seq` (`1..32767`) |
| STOP | `cmd: "STOP"`, optional `seq` (`1..32767`) |
| PIN | `pin` (0..254), `value` (0..255), `pwm` (0 or 1), optional `seq` (`1..32767`) |
| ACT | `name`, optional `data`, primary/secondary numeric fields, optional `seq` (`1..32767`), optional `at_ms` (`0..32767`), optional `lease_ms` (`1..30000`) |

Primary ACT aliases, in precedence order: `value`, `state`, `left`, `angle`,
`steps`, `reg`, `v1`. Secondary aliases: `right`, `val`, `v2`.
Command numbers are signed 16-bit integers; strings, booleans, fractions and overflow
are invalid. Every outgoing command from `RemoteSwarmNode` includes an optional
monotonically increasing `seq` (`1..32767`, wrapping at `32767 -> 1`) unless adding
`seq` would exceed `max_command_bytes`. Slaves validate `seq` (`1..32767`) when
present. Ordering uses the ring of **32767** values (zero is excluded):
`distance = (seq - last_seq) mod 32767`. An empty session accepts any valid sequence;
otherwise only distances `1..16383` advance the watermark. Duplicate or stale
`ACT`/`PIN` packets are ignored and increment `seq_drop`. Newer `PING` and `STOP`
advance the same watermark; delayed/duplicate controls never rewind it. A stale
`PING` still receives STATE, and a stale `STOP` still stops actuators and cancels
pending commands. Only watchdog recovery or a changed Master endpoint resets
ordering. Comparisons require less than half a cycle of separation, with one
sender allocating sequences for all commands in a session. Legacy packets without
`seq` remain supported and bypass ordering; this is not cryptographic replay protection.
Whenever
`_lastCmdSeq > 0`, Slaves include `"ack": _lastCmdSeq` in outgoing `STATE` packets,
allowing `RemoteSwarmNode` to compute Round-Trip Time (`rtt_ms`), RFC 3550 smoothed
jitter (`jitter_ms`), and Master-to-Slave clock offset (`clock_offset_ms`). `ack`
is a receive watermark, not confirmation of scheduled execution or physical motion;
it also covers controls and may advance before an actuator deadline is reached.

Optional `"at_ms"` (`0..32767`) on `ACT` commands specifies a 15-bit modular target
Slave `uptime_ms` (`target_slave_ms & 0x7FFF`). Slaves compute the signed modular
delay `delta_ms = ((at_ms - (uptime_ms & 0x7FFF) + 16384) & 0x7FFF) - 16384`. When
`1 <= delta_ms <= 1000`, the Slave queues/overwrites a 1-slot pending actuation for
that actuator and executes it when `uptime_ms` reaches the target time; if `at_ms` is
omitted, `delta_ms <= 0`, or `delta_ms > 1000`, the command executes immediately.
All pending scheduled actuations are immediately cleared on `STOP` or watchdog
timeout. `SwarmMaster.sync_actuate()` uses `clock_offset_ms` and `at_ms` to align
multi-node actuations toward a common estimated deadline. Actual skew depends on
clock-estimation error, timestamp quantization, arrival before that deadline, and
each Slave's polling/blocking time; no exact physical synchronization is guaranteed.

Optional `"lease_ms"` (`1..30000`) on `ACT` commands sets an application-level
command lease on that specific actuator independent of transport `PING` heartbeats.
If no new `ACT` command for that actuator arrives before `lease_ms` elapses (counted
from execution time, including after a scheduled `at_ms` command fires), the Slave
automatically applies safe-stop rules to that actuator and increments a `_leaseExpirations`
(`lease_exp`) counter even while background `PING` keepalives continue to arrive.
Across `STOP`, transport watchdog timeout (`wd_trips`), and `lease_ms` expiration (`lease_exp`),
Slaves zero `L298N`, `DRV8833`, `MOTOR_2PIN`, `STEPPER`, `PWM_OUT`, and `DAC_OUT`
outputs (`(0, 0, "")`), release `SERVO` pulse holding (`bus_addr = 0` on Arduino,
`holding = False` on Linux), and invoke `CUSTOM` actuator callbacks with `(0, 0, "STOP")`.
An unknown Linux actuator is ignored. A supported registration must not
silently pretend to provide an unimplemented driver.

Firmware commands are flat objects with integer/string fields. The allocation-free
parser handles JSON quote, backslash and control-character escapes. Send Unicode as
UTF-8 (the Python SDK does); firmware rejects `\u` escapes rather than misinterpreting
them. Firmware names use 1..15 ASCII letters/digits/underscores/hyphens; node IDs use
1..19. Registration returns false for invalid hardware names. Firmware string payloads
are limited to 31 decoded bytes. Firmware integer parsing rejects invalid or overflowing
values rather than converting them to zero or wrapping.

Arduino HELLO and STATE buffers remain 256 and 384 bytes respectively; overflow can
omit later entries. This is a known limitation, not negotiated complete-sample support.

## Session lifecycle

Discovery and `get()` are passive. `subscribe()` or an actuator command opts a node
into keepalive traffic. `connect()` additionally waits for a fresh valid STATE before
returning and raises TimeoutError otherwise. `disconnect()` stops that active node and
removes it from keepalive traffic. `close()` stops active nodes, joins workers and
closes sockets; it is idempotent and is also available as a context manager.

This bookkeeping does not prevent multiple independent masters from controlling a
node. Sequence numbers (`seq`) and `STATE` acknowledgements (`ack`) reject stale
out-of-order `ACT`/`PIN` commands within a single Master session and estimate RTT,
jitter, and clock offset, while cryptographic replay protection, command expiry, and
authentication remain in the root README backlog.
