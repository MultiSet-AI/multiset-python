"""go2-credentials -- fetch the AES key and serial, write them to .env."""

from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from multiset.vps.settings import find_env_file

from ..credentials import REGIONS, fetch_credentials, find_serial, save_to_env
from ._common import add_common, run, setup_logging


def _body(args: argparse.Namespace) -> int:
    serial = args.serial
    if not serial and not args.no_multicast:
        # Best-effort: the serial pairs this robot with the right cloud row,
        # but plenty of networks drop multicast.
        found = find_serial(timeout=args.timeout)
        if len(found) == 1:
            serial, ip = next(iter(found.items()))
            print(f"found {serial} at {ip}")
        elif found:
            for i, (sn, ip) in enumerate(found.items()):
                print(f"  [{i}] {sn}  at {ip}")
            serial = list(found)[int(input("which robot? "))]

    password = getpass.getpass(f"Unitree password for {args.email}: ")
    devices = fetch_credentials(args.email, password, region=args.region, serial=serial)

    print()
    for device in devices:
        print(f"  {device.redacted()}")

    keyed = [d for d in devices if d.has_key]
    if not keyed:
        print(
            "\nNone of these robots exposes an AES key. That firmware predates the\n"
            "encrypted handshake (data2=3), so you do not need one -- leave\n"
            "GO2_AES_KEY empty."
        )
        return 0

    chosen = keyed[0]
    if len(keyed) > 1:
        # Never guess: another robot's key fails later as an auth error.
        for i, device in enumerate(keyed):
            print(f"  [{i}] {device.redacted()}")
        chosen = keyed[int(input("\nwhich robot is this? "))]

    if not args.save:
        print("\n(re-run with --save to write GO2_SN and GO2_AES_KEY into .env)")
        return 0

    target = Path(args.env) if args.env else (find_env_file() or Path.cwd() / ".env")
    save_to_env(chosen, target)
    print(f"\nwrote GO2_SN and GO2_AES_KEY -> {target}")
    print("next: set GO2_IP if it is not already there, then localize.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = add_common(
        argparse.ArgumentParser(
            prog="go2-credentials",
            description="Fetch this robot's AES-128 key and serial from Unitree's cloud.",
            epilog="The key is a per-device secret held in Unitree's cloud. It cannot be "
            "derived locally, and it cannot be obtained from the robot's IP.",
        )
    )
    parser.add_argument("--email", required=True, help="Unitree account email")
    parser.add_argument("--region", default="global", choices=REGIONS)
    parser.add_argument("--serial", default=None, help="skip multicast; use this serial")
    parser.add_argument("--no-multicast", action="store_true", help="do not look for a serial")
    parser.add_argument("--save", action="store_true", help="write the result into .env")
    parser.add_argument("--timeout", type=float, default=3.0, help="multicast wait (default 3)")
    args = parser.parse_args(argv)
    setup_logging(args)
    return run(_body, args)


if __name__ == "__main__":
    raise SystemExit(main())
