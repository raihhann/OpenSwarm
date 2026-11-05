"""
OpenSwarm Linux Slave CLI (`openswarm-slave`)
Turns any Linux SBC (Arduino UNO Q, Portenta X8, Raspberry Pi, Jetson) or laptop
into an active OpenSwarm Slave node right from the terminal.
"""

import argparse
from .node import SwarmNode


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenSwarm Linux Slave Agent")
    parser.add_argument("--id", default="linux_node", help="Slave Node ID (default: linux_node)")
    parser.add_argument("--port", type=int, default=4210, help="UDP Port (default: 4210)")
    parser.add_argument("--led-pin", type=int, default=2, help="Register a GPIO pin as 'led' (default: 2)")
    args = parser.parse_args()

    node = SwarmNode(args.id, udp_port=args.port)
    node.register_digital_output("led", args.led_pin)
    node.register_cpu_temp("cpu_temp")
    node.register_system_load("sys_load")
    node.register_wifi_rssi("rssi")
    node.start(block=True)


if __name__ == "__main__":
    main()
