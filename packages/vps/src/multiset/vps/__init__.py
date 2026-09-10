"""MultiSet visual positioning: an image and its intrinsics in, a pose out.

    import cv2
    from multiset.vps import PinholeIntrinsics, localize_image

    image = cv2.imread("rectified.png")
    K = PinholeIntrinsics(fx=728.47, fy=727.57, px=646.64, py=346.46,
                          width=1280, height=720)
    pose = localize_image(image, K)
    if pose:
        print(pose.x, pose.y, pose.yaw_deg, pose.confidence)

Anything implementing the FrameSource protocol can be localized directly:

    pose = localize(source)

This package logs rather than prints, and raises MultisetError subclasses
rather than exiting:

    import logging; logging.basicConfig(level=logging.INFO)
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

from .client import (
    EQUIRECT_JPEG_BUDGET,
    MAX_EQUIRECT_WIDTH,
    MAX_IMAGE_DIM,
    VPSClient,
    encode_equirect,
    pose_to_hint,
)
from .errors import (
    CalibrationError,
    CameraError,
    ConfigError,
    FrameTimeout,
    MultisetError,
    VPSAuthError,
    VPSError,
)
from .frames import (
    CAM_TO_OPTICAL,
    HANDHELD,
    YUP_TO_ZUP,
    Mount,
    camera_pose_to_origin,
    quaternion_matrix,
)
from .intrinsics import (
    FisheyeCalibration,
    PinholeIntrinsics,
    Rectifier,
    intrinsics,
    undistort,
)
from .localize import localize, localize_image, localize_panorama
from .pose import Pose
from .settings import DEFAULT_API_BASE, VPSSettings, find_env_file, parse_env_file
from .sources import Frame, FrameSource, Panorama, PanoramaSource

try:
    __version__ = version("multiset-vps")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0.dev0"

# Silences "no handler could be found" without touching the app's logging.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "CAM_TO_OPTICAL",
    "DEFAULT_API_BASE",
    "EQUIRECT_JPEG_BUDGET",
    "HANDHELD",
    "MAX_EQUIRECT_WIDTH",
    "MAX_IMAGE_DIM",
    "YUP_TO_ZUP",
    "CalibrationError",
    "CameraError",
    "ConfigError",
    "FisheyeCalibration",
    "Frame",
    "FrameSource",
    "FrameTimeout",
    "Mount",
    "MultisetError",
    "Panorama",
    "PanoramaSource",
    "PinholeIntrinsics",
    "Pose",
    "Rectifier",
    "VPSAuthError",
    "VPSClient",
    "VPSError",
    "VPSSettings",
    "__version__",
    "camera_pose_to_origin",
    "encode_equirect",
    "find_env_file",
    "intrinsics",
    "localize",
    "localize_image",
    "localize_panorama",
    "parse_env_file",
    "pose_to_hint",
    "quaternion_matrix",
    "undistort",
]
