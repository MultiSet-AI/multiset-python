"""Shared plumbing for the CLIs: logging, error reporting, .env writing."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable

from multiset.vps import MultisetError

log = logging.getLogger("multiset")


def add_common(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--env", default=None, metavar="FILE", help="use this .env")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="-v for info, -vv for debug"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="errors only")
    return parser


def setup_logging(args: argparse.Namespace) -> None:
    """Wire the library's logs to stderr at the requested level.

    stderr, not stdout: a CLI's stdout is its result, and a progress line must
    not end up in whatever the user pipes it into.
    """
    level = (
        logging.ERROR
        if args.quiet
        else (logging.INFO, logging.INFO, logging.DEBUG)[min(args.verbose, 2)]
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger("multiset")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # Do NOT propagate to the root logger. A dependency (the WebRTC transport
    # among them) may have called logging.basicConfig(), which installs a root
    # handler -- and every record would then be printed twice, once by each.
    root.propagate = False


def run(main: Callable[[argparse.Namespace], int], args: argparse.Namespace) -> int:
    """Call a CLI body, turning MultisetError into a message and exit code 1.

    Users get the sentence, not a traceback; -v adds the traceback back for
    anyone debugging.
    """
    try:
        return main(args)
    except MultisetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if args.verbose:
            raise
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
