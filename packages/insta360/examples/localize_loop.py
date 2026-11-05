#!/usr/bin/env python
"""Keep localizing, printing each fix. The hints chain, so it speeds up.

python examples/localize_loop.py --count 10
python examples/localize_loop.py --device 1 --interval 5
"""

from __future__ import annotations

import argparse
import logging

from multiset.insta360 import Insta360Error, Localizer, UsbCamera
from multiset.vps import MultisetError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", help="camera index or /dev/videoN; default: auto-detect")
    parser.add_argument("--map", metavar="MAP_CODE")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--count", type=int, default=0, help="0 = until Ctrl-C")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        device = int(args.device) if args.device and args.device.isdigit() else args.device
        camera = UsbCamera(device)
    except Insta360Error as exc:
        print(f"camera: {exc}")
        return 1

    with camera:
        print(f"camera up: {camera.resolution[0]}x{camera.resolution[1]} equirect")
        loc = Localizer(camera, map_code=args.map)
        found = 0
        try:
            for index, pose in enumerate(loc.stream(interval=args.interval), start=1):
                if pose:
                    found += 1
                    print(
                        f"{index:3d}  x {pose.x:+7.3f}  y {pose.y:+7.3f}  "
                        f"yaw {pose.yaw_deg:+7.1f}  conf {pose.confidence:.3f}"
                    )
                else:
                    print(f"{index:3d}  no pose")
                if args.count and index >= args.count:
                    break
        except KeyboardInterrupt:
            print()
        except MultisetError as exc:
            print(f"failed: {exc}")
            return 1
    print(f"{found} fixes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
