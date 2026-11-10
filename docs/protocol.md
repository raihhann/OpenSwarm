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
(complete sample of numeric values or lists of one to six values). Nonfinite values
are invalid. Linux adds `sensor_errors`, mapping omitted sensors to error descriptions.
A later successful sample clears those errors. A callback returning an invalid shape
or failing does not terminate Linux telemetry generation.

## Commands

| Command | Fields |
| --- | --- |
| PING | `cmd: "PING"` |
| STOP | `cmd: "STOP"` |
| PIN | `pin` (0..254), `value` (0..255), `pwm` (0 or 1) |
| ACT | `name`, optional `data`, primary/secondary numeric fields |

Primary ACT aliases, in precedence order: `value`, `state`, `left`, `angle`,
`steps`, `reg`, `v1`. Secondary aliases: `right`, `val`, `v2`.
Command numbers are signed 16-bit integers; strings, booleans, fractions and overflow
are invalid. An unknown Linux actuator is ignored. A supported registration must not
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
node. UDP commands have no acknowledgements, sequence numbers, replay protection,
command expiry, or authentication. Those items remain in the root README backlog.
