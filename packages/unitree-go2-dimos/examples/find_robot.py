"""Step 1: find the robot's address.

    python examples/find_robot.py

Sweeps your subnet for the port only a Go2 head unit opens -- about five
seconds. A Jetson carrier board is reported too, but only when no head unit
answers: "the board is up, the robot is not" beats a bare "nothing found".
"""

import argparse
import logging

from multiset.unitree.go2.dimos import find_robots


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subnet", help="e.g. 192.168.1.0/24 (default: this machine's)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    hosts = find_robots(subnet=args.subnet)
    if not hosts:
        print("no robot found.")
        print("  is it powered on and on this wifi?")
        print("  otherwise read the address off your router's lease table")
        return 1

    for host in hosts:
        print(f"  {host}")

    robots = [h for h in hosts if h.is_robot]
    if not robots:
        print("\nfound a Jetson board but no head unit -- GO2_IP needs the host with 9991 open")
        return 1
    if len(robots) > 1:
        print(f"\n{len(robots)} robots. Pick one and set GO2_IP to it.")
        return 0
    print(f"\nGO2_IP={robots[0].ip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
