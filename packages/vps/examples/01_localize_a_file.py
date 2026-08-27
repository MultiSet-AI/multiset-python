#!/usr/bin/env python
"""multiset-vps on its own -- no robot, no camera, no device package.

Localize a frame you already have. The only thing VPS needs is a RECTIFIED image
and the pinhole intrinsics describing that exact image.

    python packages/vps/examples/01_localize_a_file.py rectified.png

Where do the intrinsics come from? Whatever produced the image. If it came off a
Go2, multiset.unitree.go2.FRONT.intrinsics is that camera's answer. If it came
from your own rig, it is your calibration's rectified set -- and it must describe
the image AFTER undistortion, not the raw sensor.
"""

from __future__ import annotations

import argparse
import logging

import cv2
from multiset.vps import MultisetError, PinholeIntrinsics, localize_image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="an ALREADY-RECTIFIED image")
    parser.add_argument("--fx", type=float, default=728.474824)
    parser.add_argument("--fy", type=float, default=727.571939)
    parser.add_argument("--px", type=float, default=646.640703)
    parser.add_argument("--py", type=float, default=346.461648)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    image = cv2.imread(args.image)
    if image is None:
        print(f"cannot read {args.image}")
        return 1
    height, width = image.shape[:2]
    K = PinholeIntrinsics(
        fx=args.fx, fy=args.fy, px=args.px, py=args.py, width=width, height=height
    )

    try:
        # Credentials come from .env: MULTISET_CLIENT_ID / _SECRET / _MAP_CODE.
        pose = localize_image(image, K)
    except MultisetError as exc:
        print(f"error: {exc}")
        return 1

    if not pose:
        # Not a failure -- the view simply did not match the map.
        print(pose)
        return 2
    print(f"{pose}\nyaw {pose.yaw_deg:+.1f} deg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
