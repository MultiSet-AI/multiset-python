"""Hold the link open and localize repeatedly.

    python examples/localize_loop.py --count 10

One connection for the whole loop: reconnecting per query costs several seconds
each time, and the token is cached on the client for 30 minutes.
"""

import argparse
import logging
import time

from multiset.unitree.go2.dimos import Go2
from multiset.vps import MultisetError

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    found = 0
    try:
        with Go2.from_env() as dog:
            for i in range(args.count):
                started = time.time()
                pose = dog.localize()
                if pose:
                    found += 1
                    print(f"{i + 1:3d}  {pose}")
                else:
                    print(f"{i + 1:3d}  no pose ({pose.response_ms:.0f} ms)")
                time.sleep(max(0.0, args.interval - (time.time() - started)))
    except MultisetError as exc:
        print(f"error: {exc}")
        return 1

    print(f"\n{found}/{args.count} localized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
