"""Matching GPIO fixture for the Raspberry Pi; explicitly refuses silent simulation."""
import argparse
import time

from openswarm_slave import SwarmNode
from openswarm_slave.hal_linux import LinuxHAL


def create_probe(pin=None, simulation=False, node_id="probe_rpi", port=4210):
    hal = LinuxHAL(backend="sim" if simulation else "auto", verbose_sim=False)
    if not simulation and hal.capabilities["backend"] == "sim":
        raise RuntimeError("No real GPIO backend available; do not record this as hardware evidence")
    if pin is not None:
        hal.setup_pin(pin, "OUT")
        hal.digital_write(pin, 0)
    node = SwarmNode(node_id, udp_port=port, hal=hal)
    state = dict(value=0, acts=0, stops=0, hold_ms=0, exec_ms=0)
    on = [time.monotonic()]

    def apply(value, secondary, data):
        now = time.monotonic()
        if data == "STOP":
            if state["value"]:
                state["hold_ms"] = round((now - on[0]) * 1000, 3)
            state["value"] = 0
            state["stops"] += 1
        else:
            state["value"] = value
            state["acts"] += 1
            state["exec_ms"] = int((now - node._start_time) * 1000) & 0x7FFF
            on[0] = now
        if pin is not None:
            hal.digital_write(pin, int(state["value"] != 0))

    node.register_custom_actuator("probe", apply)
    for name in state:
        node.register_custom_sensor(name, lambda key=name: state[key])
    return node


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pin", type=int, required=True, help="GPIO line number for the selected backend")
    args = parser.parse_args()
    fixture = create_probe(args.pin)
    print("GPIO backend:", fixture.hal.capabilities)
    try:
        fixture.start()
    except KeyboardInterrupt:
        pass
    finally:
        fixture.stop()
