#!/usr/bin/env python
"""Localize a 360 panorama from disk -- no camera, no robot, no hardware.

The equirect counterpart of 01_localize_a_file.py, and the quickest way to
check that credentials, network and map all work before any hardware is
involved.

    python 02_localize_a_panorama.py room.jpg

The image must be equirectangular: 2:1, the whole room in one frame, as an
Insta360 in 360 webcam mode or any 360 camera's photo mode produces. Unlike a
normal photo it needs no lens numbers -- the projection is described by the 2:1
shape itself.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import cv2
from multiset.vps import CalibrationError, MultisetError, localize_panorama


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="a 2:1 equirectangular image")
    parser.add_argument("--map", metavar="MAP_CODE", help="override MULTISET_MAP_CODE")
    parser.add_argument(
        "--attempts",
        type=int,
        default=8,
        help="retries while the query instance wakes (default: 8)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)-7s %(name)s: %(message)s",
    )

    if not args.image.is_file():
        print(f"no such file: {args.image}", file=sys.stderr)
        return 1
    image = cv2.imread(str(args.image))
    if image is None:
        print(f"could not read {args.image} as an image", file=sys.stderr)
        return 1

    height, width = image.shape[:2]
    print(f"{args.image.name}: {width}x{height}")

    query: dict[str, object] = {"attempts": args.attempts}
    if args.map:
        query["map_code"] = args.map

    try:
        pose = localize_panorama(image, **query)
    except CalibrationError as exc:
        # Raised before anything is uploaded, so this costs nothing.
        print(f"\nnot a panorama: {exc}", file=sys.stderr)
        return 1
    except MultisetError as exc:
        print(f"\nfailed: {exc}", file=sys.stderr)
        return 1

    if pose:
        print(
            f"\n  x {pose.x:+.3f}  y {pose.y:+.3f}  z {pose.z:+.3f}"
            f"   heading {pose.yaw_deg:+.1f} deg   confidence {pose.confidence:.3f}"
            f"   ({pose.response_ms:.0f} ms)"
        )
        return 0
    print(f"\n  no pose: {pose.raw.get('message') or 'the map did not recognise it'}")
    print("  The picture has to be taken inside the map you are querying.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
