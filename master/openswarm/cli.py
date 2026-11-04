"""
OpenSwarm Command-Line Interface (`openswarm`)
Allows scanning for Slave nodes, monitoring live telemetry, and testing LED/pins directly from terminal.
"""

import argparse
import time
from .master import SwarmMaster


def cmd_scan(args: argparse.Namespace) -> None:
    master = SwarmMaster()
    print(f"Scanning local network for OpenSwarm Slave nodes ({args.wait:.1f}s)...")
    nodes = master.discover_all(wait_seconds=args.wait)
    if not nodes:
        print("No Slave nodes discovered via UDP broadcast.")
        print("Tip: If your Wi-Fi router blocks UDP broadcast, use `--ip <SLAVE_IP>` in commands.")
    else:
        print(f"\nDiscovered {len(nodes)} Slave Node(s):")
        print("-" * 78)
        for node in nodes.values():
            print(f"  Node ID   : {node.node_id} ({node.board})")
            print(f"  Address   : {node.ip}:{node.port}")
            print(f"  Actuators : {node.declared_actuators}")
            print(f"  Sensors   : {node.sensors}")
            print("-" * 78)
    master.close()


def cmd_blink(args: argparse.Namespace) -> None:
    master = SwarmMaster()
    node = master.connect(args.node, ip=args.ip, timeout=args.timeout)
    print(f"\nConnected to '{node.node_id}' at {node.ip}:{node.port}!")
    print(f"Blinking '{args.actuator}' (Ctrl+C to stop)...\n")

    state = False
    try:
        while True:
            state = not state
            node.digital_write(args.actuator, state)
            print(
                f"  -> LED={'ON ' if state else 'OFF'} | "
                f"Uptime={node.uptime_ms / 1000.0:.1f}s | "
                f"Sensors={node.sensors}"
            )
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nTurning LED OFF and closing Master connection...")
        node.digital_write(args.actuator, 0)
        master.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenSwarm Linux Master CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # openswarm scan
    p_scan = sub.add_parser("scan", help="Auto-discover all OpenSwarm Slave nodes on Wi-Fi")
    p_scan.add_argument("--wait", type=float, default=2.5, help="Scan duration in seconds")
    p_scan.set_defaults(func=cmd_scan)

    # openswarm blink <node_id>
    p_blink = sub.add_parser("blink", help="Blink a registered LED/Digital output on a Slave node")
    p_blink.add_argument("node", nargs="?", default="esp32_node", help="Slave Node ID (default: esp32_node)")
    p_blink.add_argument("--ip", type=str, default=None, help="Optional Slave IP address (e.g. 192.168.0.118)")
    p_blink.add_argument("--actuator", type=str, default="led", help="Actuator name (default: led)")
    p_blink.add_argument("--interval", type=float, default=0.5, help="Blink interval in seconds")
    p_blink.add_argument("--timeout", type=float, default=8.0, help="Discovery timeout in seconds")
    p_blink.set_defaults(func=cmd_blink)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
