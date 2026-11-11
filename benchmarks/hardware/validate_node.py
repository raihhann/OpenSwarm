"""Real UDP regression/lease tests for the probe fixture. No SwarmMaster may run alongside it."""
import argparse
import json
import platform
import socket
import subprocess
import time
from pathlib import Path


class ObservationError(RuntimeError):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


class Session:
    def __init__(self, ip, port, log):
        self.peer = (socket.gethostbyname(ip), port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", 0))
        self.sock.settimeout(0.05)
        self.log = log
        self.phase = "initialization"
        self.keepalive = False
        self.next_ping = 0
        self.allow_reset = True
        self.last_state = None
        self.armed = False
        self.retries = 0

    def send(self, packet):
        self.log.append(dict(direction="tx", host_mono_s=time.monotonic(), packet=packet,
                             phase=self.phase, local_endpoint=list(self.sock.getsockname()), peer=list(self.peer)))
        self.sock.sendto(json.dumps(packet, separators=(",", ":")).encode(), self.peer)

    def receive(self):
        try:
            data, address = self.sock.recvfrom(4096)
        except socket.timeout:
            return None
        if address != self.peer:
            return None
        packet = json.loads(data)
        self.log.append(dict(direction="rx", host_mono_s=time.monotonic(), packet=packet,
                             phase=self.phase, local_endpoint=list(self.sock.getsockname()), peer=list(address)))
        if packet.get("type") != "STATE":
            return None
        previous = self.last_state
        if previous and packet["uptime_ms"] < previous["uptime_ms"]:
            return None  # Preserve raw packet but do not satisfy predicates with reordered telemetry.
        self.last_state = packet
        if not self.allow_reset and previous:
            if self.keepalive and packet.get("wd_trips", 0) > previous.get("wd_trips", 0):
                raise ObservationError("watchdog_during_schedule", "Watchdog tripped despite scheduling keepalives")
            if (self.armed and not packet.get("ack") and
                    packet.get("wd_trips", 0) == previous.get("wd_trips", 0)):
                raise ObservationError("unexpected_session_reset", "ACK disappeared without a watchdog event; check endpoints, competing masters and firmware")
        if packet.get("ack"):
            self.armed = True
        return packet

    def wait(self, predicate, timeout=1, on_tick=None):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.keepalive and time.monotonic() >= self.next_ping:
                self.send({"cmd": "PING"})
                self.next_ping = time.monotonic() + 0.1
            if on_tick:
                on_tick()
            packet = self.receive()
            if packet is not None and predicate(packet):
                return packet
        raise ObservationError("observation_timeout", "Expected STATE not observed; retain packet log, do not infer success")

    def step(self, packet, ack, retry=False, **sensors):
        self.send(packet)
        self.send({"cmd": "PING"})  # Unsequenced observation: never advances the test watermark.
        started = time.monotonic()
        attempts = [1]
        def retry_command():
            if retry and attempts[0] < 3 and time.monotonic() - started >= attempts[0] * 0.1:
                attempts[0] += 1
                self.retries += 1
                self.send(packet)  # Same seq: never reapply an already accepted ACT.
                self.send({"cmd": "PING"})
        return self.wait(lambda p: p.get("ack") == ack and
                         all(p.get("sensors", {}).get(k) == v for k, v in sensors.items()), on_tick=retry_command)

    def begin_case(self, name):
        self.phase = name + "/reset"
        self.keepalive = False
        self.allow_reset = True
        self.armed = False
        self.send({"cmd": "STOP"})
        self.send({"cmd": "PING"})
        before = self.wait(lambda p: "acts" in p.get("sensors", {}) and p["sensors"]["value"] == 0)
        # One source endpoint throughout the run. Explicitly observe a watchdog
        # epoch boundary instead of switching sockets to reset sequence numbers.
        self.wait(lambda p: p.get("wd_trips", 0) > before.get("wd_trips", 0), timeout=1.5)
        self.send({"cmd": "PING"})
        initial = self.wait(lambda p: not p.get("ack") and p["sensors"]["value"] == 0)
        self.phase = name
        self.allow_reset = name == "watchdog_without_ping"
        return initial

    def close(self):
        self.send({"cmd": "STOP"})
        self.sock.close()


def run(ip, port=4210):
    log, cases = [], []
    session = Session(ip, port, log)

    def case(name, operation):
        try:
            initial = session.begin_case(name)
            detail = operation(session, initial)
            cases.append(dict(name=name, status="PASS", detail=detail))
        except Exception as exc:
            cases.append(dict(name=name, status="FAIL", error=str(exc),
                              error_kind=getattr(exc, "kind", type(exc).__name__), phase=session.phase,
                              last_state=session.last_state))
        finally:
            session.keepalive = False
            session.allow_reset = True
            session.send({"cmd": "STOP"})

    def act(seq, value, **fields):
        return dict(cmd="ACT", name="probe", seq=seq, value=value, **fields)

    def reordered(s, base):
        count = base["sensors"]["acts"]
        drops = base.get("seq_drop", 0)
        s.step(act(10, 100), 10, value=100, acts=count + 1)
        s.step(act(11, 110), 11, value=110, acts=count + 2)
        s.step(dict(cmd="PING", seq=9), 11, value=110)
        result = s.step(act(10, 100), 11, value=110, acts=count + 2)
        result = s.wait(lambda p: p.get("seq_drop", 0) == drops + 1) if result.get("seq_drop", 0) != drops + 1 else result
        s.step(dict(cmd="STOP", seq=8), 11, value=0)
        s.step(act(10, 100), 11, value=0, acts=count + 2)
        s.wait(lambda p: p.get("seq_drop", 0) == drops + 2 and p["sensors"]["value"] == 0)
        return dict(final_ack=11, stale_act_applied=False, stop_honored=True, observed_state=result)

    def wrap(s, base):
        count = base["sensors"]["acts"]
        s.step(act(32766, 1), 32766, value=1)
        s.step(dict(cmd="PING", seq=32767), 32767)
        s.step(act(1, 2), 1, value=2)
        s.step(dict(cmd="PING", seq=32766), 1)
        s.step(act(32767, 99), 1, value=2, acts=count + 2)
        s.wait(lambda p: p.get("seq_drop", 0) == base.get("seq_drop", 0) + 1)
        return s.step(act(2, 3), 2, value=3, acts=count + 3)

    def scheduled(s, base):
        s.keepalive = True
        s.next_ping = time.monotonic() + 0.1
        count = base["sensors"]["acts"]
        target = (int(base["uptime_ms"]) + 500) & 0x7FFF
        s.step(act(10, 120, at_ms=target), 10, acts=count)
        s.step(dict(cmd="PING", seq=9), 10, acts=count)
        s.send(act(8, 99))
        s.wait(lambda p: p.get("seq_drop", 0) == base.get("seq_drop", 0) + 1)
        observed = s.wait(lambda p: p["sensors"]["acts"] == count + 1 and p["sensors"]["value"] == 120)
        error = ((int(observed["sensors"]["exec_ms"]) - target + 16384) & 0x7FFF) - 16384
        if error < 0:
            raise AssertionError("Scheduled callback executed before its target")
        target2 = (int(observed["uptime_ms"]) + 500) & 0x7FFF
        s.step(act(11, 130, at_ms=target2), 11, retry=True, acts=count + 1)
        s.step(dict(cmd="STOP", seq=7), 11, retry=True, value=0)
        end = time.monotonic() + 0.55
        while time.monotonic() < end:
            s.send({"cmd": "PING"})
            s.receive()
            time.sleep(0.03)
        final = s.step(dict(cmd="PING"), 11, value=0, acts=count + 1)
        return dict(target_ms=target, execution_lateness_ms=error, pending_stop_cancelled=True,
                    delivery_retries=s.retries, final_state=final)

    def timed(s, base, lease=None, ping=True):
        count = base["sensors"]["acts"]
        fields = {} if lease is None else {"lease_ms": lease}
        s.step(act(1, 100, **fields), 1, value=100, acts=count + 1)
        start = time.monotonic()
        next_ping = start + 0.2
        last, states = None, []
        # Application sends no further ACT. Continue PING only in deadlock trials.
        while time.monotonic() - start < 2.2:
            if ping and time.monotonic() >= next_ping:
                s.send({"cmd": "PING"})
                next_ping += 0.2
            packet = s.receive()
            if packet:
                last = packet
                states.append(packet)
        if last is None:
            raise AssertionError("No telemetry during observation")
        sensors = last["sensors"]
        if lease is not None or not ping:
            if sensors["value"] != 0:
                raise AssertionError("Output did not stop")
            counter = "lease_exp" if lease is not None else "wd_trips"
            if last.get(counter, 0) != base.get(counter, 0) + 1:
                raise AssertionError("Stop reason counter incorrect")
            duration = sensors["hold_ms"]
            minimum = lease if lease is not None else 500
            if duration < minimum:
                raise AssertionError("Output stopped earlier than the configured deadline")
            return dict(onboard_hold_ms=duration, target_ms=minimum,
                        deadline_excess_ms=duration - minimum, final_state=last)
        if any(p["sensors"]["value"] != 100 for p in states):
            raise AssertionError("No-lease control did not remain active")
        return dict(energized_for_at_least_s=2.2, right_censored=True, final_state=last)

    case("delayed_ping_and_stale_stop", reordered)
    case("sequence_wraparound", wrap)
    case("scheduled_preservation_and_stop_cancellation", scheduled)
    case("lease_150ms_with_5hz_ping", lambda s, b: timed(s, b, 150))
    case("lease_450ms_with_5hz_ping", lambda s, b: timed(s, b, 450))
    case("no_lease_with_5hz_ping", lambda s, b: timed(s, b))
    case("watchdog_without_ping", lambda s, b: timed(s, b, ping=False))
    session.close()
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=3).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        revision, dirty = "unknown", "unknown"
    return dict(schema_version=2, source_endpoint_policy="one socket per run; watchdog reset observed between cases",
                kind="live UDP probe; operator must record physical board and flashed source",
                peer=[ip, port], host=platform.platform(), revision=revision,
                worktree_status=dirty, cases=cases, packet_log=log,
                limitations="hold_ms is callback timing using the slave clock, not motor stopping time. PASS verifies functional observations; timing excess must be reviewed separately. No independent cross-board timing measurement.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", required=True)
    parser.add_argument("--port", type=int, default=4210)
    parser.add_argument("--output", type=Path, required=True, help="Use a distinct file for every board/run")
    args = parser.parse_args()
    result = run(args.ip, args.port)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for item in result["cases"]:
        print(item["status"], item["name"], item.get("error", ""))
    print("Saved", args.output)
    raise SystemExit(int(any(case["status"] != "PASS" for case in result["cases"])))
