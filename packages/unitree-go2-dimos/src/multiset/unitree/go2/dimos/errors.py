"""Failures specific to the Go2, plus the shared ones re-exported.

Go2Error inherits from multiset.vps.MultisetError, so one except clause covers
both packages. Frame timeouts and calibration mismatches are not Go2-only, so
they stay in multiset.vps and are re-exported here -- the SAME classes, not
parallel ones.
"""

from __future__ import annotations

from multiset.vps.errors import (
    CalibrationError,
    CameraError,
    ConfigError,
    FrameTimeout,
    MultisetError,
    VPSAuthError,
    VPSError,
)


class Go2Error(MultisetError):
    """Base for every Go2-specific error."""


class ConnectionFailed(Go2Error):
    """The WebRTC link could not be established."""


class SignallingUnavailable(ConnectionFailed):
    """Nothing is listening on the robot's signalling port.

    Usually the wrong address. A Go2 with a Jetson board puts TWO computers on
    the wifi:

        head unit   port 9991 ONLY, no SSH, no web page -- this is GO2_IP
        Jetson      22, 80, 111, 4000 -- never serves WebRTC

    The head unit also opens 9991 late in its boot.
    """


class AuthenticationError(ConnectionFailed):
    """The robot rejected the AES-128 key.

    Per-device, and only obtainable from Unitree's cloud. See
    credentials.fetch_credentials().
    """


class VizNotInstalled(Go2Error):
    """The example visualisation needs the viz extra."""

    def __init__(self) -> None:
        super().__init__(
            "the visualisation example needs the viz extra:\n"
            "    pip install 'multiset-unitree-go2-dimos[viz]'\n"
            "It is optional because open3d alone is ~284 MB installed, and it "
            "resolves only on Python 3.10-3.12 -- on anything newer the extra "
            "installs nothing, because open3d has no wheel."
        )


__all__ = [
    "AuthenticationError",
    "CalibrationError",
    "CameraError",
    "ConfigError",
    "ConnectionFailed",
    "FrameTimeout",
    "Go2Error",
    "MultisetError",
    "SignallingUnavailable",
    "VPSAuthError",
    "VPSError",
    "VizNotInstalled",
]
