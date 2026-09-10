#!/usr/bin/env python
"""One pose from a 360 camera, then exit.

    python examples/quickstart.py                      # camera on this machine
    python examples/quickstart.py --ssh unitree@IP     # camera on the robot

Needs MULTISET_CLIENT_ID, MULTISET_CLIENT_SECRET and MULTISET_MAP_CODE in a
.env file (see ../../.env.example), and the camera in Webcam mode + 360 view.
"""

from __future__ import annotations

import argparse
import logging

from multiset.insta360 import Insta360Error, SSHCamera, UsbCamera
from multiset.vps import MultisetError, localize


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh", metavar="USER@HOST", help="camera on a robot")
    parser.add_argument("--map", metavar="MAP_CODE", help="override MULTISET_MAP_CODE")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        camera = SSHCamera(args.ssh) if args.ssh else UsbCamera()
    except Insta360Error as exc:
        print(f"camera: {exc}")
        return 1

    with camera:
        print(f"camera up: {camera.resolution[0]}x{camera.resolution[1]} equirect")
        print("localizing (the first query can take a couple of minutes if the")
        print("query instance is asleep)...")
        query = {"attempts": 8}
        if args.map:
            query["map_code"] = args.map
        try:
            pose = localize(camera, **query)
        except MultisetError as exc:
            print(f"failed: {exc}")
            return 1

    if pose:
        print(
            f"\n  x {pose.x:+.3f}  y {pose.y:+.3f}  z {pose.z:+.3f}"
            f"   heading {pose.yaw_deg:+.1f} deg   confidence {pose.confidence:.3f}"
        )
        return 0
    print("\n  no pose: the map did not recognise this frame.")
    print("  Stand somewhere with more visible structure and try again.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
