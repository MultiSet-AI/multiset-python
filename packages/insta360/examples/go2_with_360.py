#!/usr/bin/env python
"""Localize a Unitree Go2 — with its own front camera, a 360 camera, or both.

The robot's front camera is a fisheye: it gets rectified, and the query carries
this robot's measured lens numbers. An Insta360 on the robot's USB is a
panorama: it sees the whole room at once and carries no lens numbers at all.

    python examples/go2_with_360.py --front              # the robot's own camera
    python examples/go2_with_360.py --360 unitree@IP     # an Insta360 on the robot
    python examples/go2_with_360.py --front --360 unitree@IP    # both, compared

Needs a .env with the three MULTISET_* values; --front also needs GO2_IP and
GO2_AES_KEY. See ../../.env.example.
"""

from __future__ import annotations

import argparse
import logging

from multiset.vps import MultisetError, Pose, VPSClient


def show(label: str, pose: Pose) -> None:
    if pose:
        print(
            f"  {label:<10} x {pose.x:+7.3f}  y {pose.y:+7.3f}  z {pose.z:+7.3f}"
            f"   yaw {pose.yaw_deg:+7.1f}   conf {pose.confidence:.3f}"
        )
    else:
        print(f"  {label:<10} no pose ({pose.raw.get('message') or 'not recognised'})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--front", action="store_true", help="use the Go2's camera")
    parser.add_argument(
        "--360", dest="ssh", metavar="USER@HOST", help="use an Insta360 on the robot, over SSH"
    )
    parser.add_argument("--map", metavar="MAP_CODE")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    if not args.front and not args.ssh:
        parser.error("pick --front, --360 USER@HOST, or both")
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)-7s %(name)s: %(message)s",
    )

    query: dict[str, object] = {}
    if args.map:
        query["map_code"] = args.map
    client: VPSClient | None = None

    try:
        # One client for every query: it caches the auth token, so a second
        # query costs one request instead of two. Built inside the try so a
        # missing .env prints the reason instead of a traceback.
        client = VPSClient()
        if args.front:
            from multiset.unitree.go2 import Go2

            with Go2.from_env() as dog:
                # A pinhole query: rectified frame + this robot's lens numbers.
                show("front", dog.localize(client=client, **query))

        if args.ssh:
            from multiset.insta360 import SSHCamera
            from multiset.vps import localize

            with SSHCamera(args.ssh) as cam:
                print(f"  360 camera: {cam.resolution[0]}x{cam.resolution[1]} equirect")
                # An equirect query: no lens numbers. attempts= rides out the
                # cold start, which can be a couple of minutes when idle.
                show("360", localize(cam, client=client, attempts=8, **query))
    except MultisetError as exc:
        print(f"error: {exc}")
        return 1
    finally:
        if client is not None:
            client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
