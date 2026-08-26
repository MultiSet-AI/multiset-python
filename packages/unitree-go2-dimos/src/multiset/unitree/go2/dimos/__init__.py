"""Visual positioning for the Unitree Go2.

Seven steps, and each one has a file:

    1. IP and credentials from .env        config.py
    2. AES key + serial (optional)         credentials.py
    3. connect to the robot                robot.py
    4. camera access                       robot.py
    5. capture and undistort               robot.py
    6. the VPS query                       multiset.vps
    7. Y-up -> Z-up                        multiset.vps

Steps 6 and 7 live in `multiset-vps` because they are not Go2-specific: the
query, the Pose and the frame conversions are identical for any camera. This
package supplies what only it can -- the WebRTC transport, the video track, and
this robot's measured numbers.

    from multiset.unitree.go2.dimos import Go2

    with Go2.from_env() as dog:
        pose = dog.localize()
        if pose:
            print(pose.x, pose.y, pose.yaw_deg, pose.confidence)

Or, for code that should not care what robot it is holding:

    from multiset.vps import localize
    pose = localize(dog)

This package logs, it does not print, and it raises Go2Error subclasses rather
than exiting. Turn logging on with:

    import logging; logging.basicConfig(level=logging.INFO)
"""

from __future__ import annotations

import logging

# Re-exported so `except FrameTimeout` works whichever import you used. These
# are the SAME classes as in multiset.vps, not parallel ones.
from multiset.vps import (
    CalibrationError,
    CameraError,
    ConfigError,
    Frame,
    FrameTimeout,
    MultisetError,
    PinholeIntrinsics,
    Pose,
    VPSAuthError,
    VPSError,
    camera_pose_to_origin,
)

from .__about__ import __version__
from .config import Go2Settings
from .credentials import Credentials, fetch_credentials, find_serial, save_to_env
from .discovery import Host, find_robots, scan_subnet
from .errors import (
    AuthenticationError,
    ConnectionFailed,
    Go2Error,
    SignallingUnavailable,
    VizNotInstalled,
)
from .robot import (
    FRONT,
    GO2_FRONT_720P,
    GO2_MOUNT,
    YUP_TO_ZUP,
    Go2,
    camera_pose_to_base,
    compose_map_from_odom,
    localize,
)

# A library that calls basicConfig() steals the application's choice. This only
# stops "no handler could be found" warnings.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "FRONT",
    "GO2_FRONT_720P",
    "GO2_MOUNT",
    "YUP_TO_ZUP",
    "AuthenticationError",
    "CalibrationError",
    "CameraError",
    "ConfigError",
    "ConnectionFailed",
    "Credentials",
    "Frame",
    "FrameTimeout",
    "Go2",
    "Go2Error",
    "Host",
    "Go2Settings",
    "MultisetError",
    "PinholeIntrinsics",
    "Pose",
    "SignallingUnavailable",
    "VPSAuthError",
    "VPSError",
    "VizNotInstalled",
    "__version__",
    "camera_pose_to_base",
    "compose_map_from_odom",
    "camera_pose_to_origin",
    "fetch_credentials",
    "find_robots",
    "find_serial",
    "localize",
    "save_to_env",
    "scan_subnet",
]
