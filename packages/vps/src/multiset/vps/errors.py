"""Every failure this package raises.

MultisetError is the root, so one except clause covers all of them. Nothing
here calls sys.exit(): SystemExit inherits from BaseException, so a caller's
`except Exception` would not catch it.
"""

from __future__ import annotations


class MultisetError(Exception):
    """Base for every error raised by any multiset.* package."""


class ConfigError(MultisetError):
    """Something needed was not configured -- no credentials, no map code."""


class CalibrationError(MultisetError):
    """A frame does not match the calibration it would be rectified with."""


class CameraError(MultisetError):
    """A frame source produced nothing usable.

    Lives here rather than in a device package because every source has the
    same two failure modes, and code written against the FrameSource protocol
    must be able to name them without importing a specific device.
    """


class FrameTimeout(CameraError):
    """No frame arrived in time."""


class VPSError(MultisetError):
    """The MultiSet VPS request failed."""


class VPSAuthError(VPSError):
    """Token request rejected -- check MULTISET_CLIENT_ID / _SECRET."""


__all__ = [
    "CalibrationError",
    "CameraError",
    "ConfigError",
    "FrameTimeout",
    "MultisetError",
    "VPSAuthError",
    "VPSError",
]
