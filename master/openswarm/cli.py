"""
OpenSwarm Command-Line Interface (`openswarm`)
Allows scanning for Slave nodes, monitoring live telemetry, and testing LED/pins directly from terminal.
"""

import argparse
import time
from .master import SwarmMaster


def cmd_scan(args: argparse.Namespace) -> None:
    with SwarmMaster() as master:
        print(f"Scanning local network for OpenSwarm nodes ({args.wait:.1f}s)...")
        nodes = master.discover_all(wait_seconds=args.wait)
        if not nodes:
            print("No nodes discovered. Use --ip if your router blocks discovery.")
        for node in nodes.values():
            print(f"  {node.node_id} ({node.board}) at {node.ip}:{node.port}")
            print(f"    Actuators: {node.declared_actuators} | Sensors: {node.declared_sensors}")


def cmd_blink(args: argparse.Namespace) -> None:
    if args.interval <= 0:
        raise ValueError("Blink interval must be positive")
    with SwarmMaster() as master:
        node = master.connect(args.node, ip=args.ip, timeout=args.timeout)
        print(f"Connected to '{node.node_id}' at {node.ip}:{node.port}")
        state = False
        try:
            while True:
                state = not state
                node.digital_write(args.actuator, state)
                print(f"LED={'ON' if state else 'OFF'} | Sensors={node.sensors}")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("Turning LED off and closing connection...")
        finally:
            node.digital_write(args.actuator, 0)


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
    try:
        args.func(args)
    except (ValueError, TimeoutError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
