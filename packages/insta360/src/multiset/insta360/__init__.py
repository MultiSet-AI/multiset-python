"""Visual positioning from an Insta360 X-series camera.

A 360 camera is the easy case for VPS: one frame sees the whole room, so there
is no aiming and nothing to calibrate. In Webcam mode + 360 view the camera is a
plain UVC device already delivering stitched frames, so there is no Insta360 SDK
here either.

    from multiset.insta360 import UsbCamera
    from multiset.vps import localize

    with UsbCamera() as cam:
        pose = localize(cam)
        if pose:
            print(pose.x, pose.y, pose.yaw_deg, pose.confidence)

For a loop, `Localizer` chains the hints so each fix speeds up the next.

This package logs, it does not print, and it raises Insta360Error subclasses
rather than exiting. Turn logging on with:

    import logging; logging.basicConfig(level=logging.INFO)
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

# Re-exported so `except CameraError` works whichever import you used. These
# are the SAME classes as in multiset.vps, not parallel ones.
from multiset.vps import (
    CameraError,
    ConfigError,
    MultisetError,
    Panorama,
    PanoramaSource,
    Pose,
    VPSAuthError,
    VPSError,
    localize,
    localize_panorama,
    pose_to_hint,
)

from .camera import DEFAULT_HEIGHT, DEFAULT_WIDTH, UsbCamera
from .errors import CameraNotFound, Insta360Error, NotPanoramic
from .localizer import DEFAULT_HINT_RADIUS, Localizer

try:
    __version__ = version("multiset-insta360")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0.dev0"

# A library that calls basicConfig() steals the application's choice. This only
# stops "no handler could be found" warnings.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "DEFAULT_HEIGHT",
    "DEFAULT_HINT_RADIUS",
    "DEFAULT_WIDTH",
    "CameraError",
    "CameraNotFound",
    "ConfigError",
    "Insta360Error",
    "Localizer",
    "MultisetError",
    "NotPanoramic",
    "Panorama",
    "PanoramaSource",
    "Pose",
    "VPSAuthError",
    "VPSError",
    "UsbCamera",
    "__version__",
    "localize",
    "localize_panorama",
    "pose_to_hint",
]
