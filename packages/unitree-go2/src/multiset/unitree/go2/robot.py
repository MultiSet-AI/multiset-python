"""Go2 -- connect, capture, localize.

This is the surface most users need:

    from multiset.unitree.go2 import Go2

    with Go2.from_env() as dog:
        pose = dog.localize()
        print(pose.x, pose.y, pose.yaw_deg, pose.confidence)

Go2 is a multiset.vps.FrameSource, so anything written against that protocol
takes it without knowing what it is:

    from multiset.vps import FisheyeCalibration, Mount, Rectifier, localize
    pose = localize(dog)

Everything underneath stays available: dog.transport for topics and commands,
dog.camera for raw frames, dog.vps for a second query against another map.
"""

from __future__ import annotations

import logging
import math
from types import TracebackType

import numpy as np
from multiset.vps import (
    YUP_TO_ZUP,  # noqa: F401  (re-exported: downstream code imports it from here)
    FisheyeCalibration,
    Frame,
    Mount,
    Pose,
    Rectifier,
    VPSClient,
    VPSSettings,
    camera_pose_to_origin,
)

from ._webrtc import RTC_TOPIC, Go2Camera, Go2Transport, quiet_decoder_warnings
from .config import Go2Settings

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# This robot's measurements. The machinery that consumes them is in multiset.vps.
# ---------------------------------------------------------------------------

WIDTH, HEIGHT = 1280, 720

# Unitree's shipped calibration. A held-out test scored it 0.3587 px against
# 0.3600 px for an in-house chessboard fit -- indistinguishable, and switching
# would move every bearing ~1.4 degrees.
GO2_FRONT_720P = FisheyeCalibration(
    name="go2-front-720p",
    fx=797.4756164864929,
    fy=796.4872112769983,
    cx=643.5352167821186,
    cy=349.2783605343087,
    k=(
        -0.07309428880537933,
        -0.02341140740909078,
        -0.0069305931780026956,
        0.009238684474464793,
    ),
    width=WIDTH,
    height=HEIGHT,
    note="Unitree default; validated against two independent in-house targets",
)

CALIBRATIONS: dict[str, FisheyeCalibration] = {GO2_FRONT_720P.name: GO2_FRONT_720P}

# base_link -> +0.30 m forward -> the front camera. A VPS pose and base_link
# differ by 0.300 m and ~90 degrees of heading.
GO2_MOUNT = Mount(
    name="go2-front",
    translation=(0.3, 0.0, 0.0),
    rotation=(-0.5, 0.5, -0.5, 0.5),
    note="front camera on the head, from the Go2 URDF mount chain",
)

#: The shared rectifier for the front camera -- built once, remap tables cached.
FRONT = Rectifier(GO2_FRONT_720P)


def camera_pose_to_base(pose_matrix: np.ndarray) -> np.ndarray:
    """A VPS camera pose -> base_link in the Z-up map frame.

    The Go2's mount chain applied to the shared conversion. Skipping it is a
    silent error rather than a visible one: measured on a real robot the camera
    pose and base_link differ by 0.300 m AND about 90 degrees of heading.
    """
    return camera_pose_to_origin(pose_matrix, GO2_MOUNT)


class Go2:
    """A connected robot: transport, camera and VPS in one object."""

    def __init__(
        self,
        settings: Go2Settings | None = None,
        vps_settings: VPSSettings | None = None,
        *,
        quiet_decoder: bool = True,
    ) -> None:
        self.settings = settings or Go2Settings.from_env()
        self.vps_settings = vps_settings
        if quiet_decoder:
            quiet_decoder_warnings()
        self.transport = Go2Transport(self.settings)
        self.camera = Go2Camera(self.transport)
        self._vps: VPSClient | None = None
        self._connected = False

    @classmethod
    def from_env(cls, env_file: str | None = None, **overrides: object) -> Go2:
        """Build from .env plus the environment, with optional overrides.

        Reads both halves of the file: the robot's address and key, and the
        MultiSet credentials. Overrides apply to the robot settings.
        """
        return cls(
            Go2Settings.from_env(env_file, **overrides),
            VPSSettings.from_env(env_file),
        )

    # -- lifecycle ---------------------------------------------------------

    def connect(self, *, video: bool = True) -> Go2:
        """Bring up the link, and the camera unless video=False."""
        if self._connected:
            return self
        self.transport.connect()
        if video:
            self.camera.start()
        self._connected = True
        return self

    def close(self) -> None:
        """Stop the camera and drop the link. Safe to call twice."""
        self.camera.stop()
        self.transport.close()
        self._connected = False

    def __enter__(self) -> Go2:
        return self.connect()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def connected(self) -> bool:
        return self._connected and self.transport.connected

    @property
    def vps(self) -> VPSClient:
        """The VPS client, built on first use.

        Lazy so that connecting to a robot does not require MultiSet
        credentials -- plenty of uses (capture, teleop, telemetry) never
        localize at all.
        """
        if self._vps is None:
            self._vps = VPSClient(self.vps_settings)
        return self._vps

    # -- the useful three --------------------------------------------------

    def frame(self, *, settle: float | None = None, timeout: float | None = None) -> np.ndarray:
        """One RAW fisheye frame, settled. Raises FrameTimeout."""
        return self.camera.fresh_frame(
            settle=self.settings.settle if settle is None else settle,
            timeout=self.settings.frame_timeout if timeout is None else timeout,
        )

    def capture(self, *, settle: float | None = None, timeout: float | None = None) -> Frame:
        """One rectified frame and the intrinsics describing it.

        The pair a pose solver needs, in memory, nothing written to disk. This
        is the FrameSource protocol's only method.
        """
        image, intrinsics = FRONT.undistort(self.frame(settle=settle, timeout=timeout))
        return Frame(image, intrinsics)

    def localize(
        self,
        *,
        settle: float | None = None,
        timeout: float | None = None,
        map_code: str | None = None,
        **query: object,
    ) -> Pose:
        """Capture, undistort and localize.

        found=False is a normal answer, not an error. Check `if pose:`.
        """
        image, intrinsics = self.capture(settle=settle, timeout=timeout)
        return self.vps.localize(image, intrinsics, map_code=map_code, **query)  # type: ignore[arg-type]

    def base_pose(self, **kwargs: object) -> tuple[float, float, float] | None:
        """(x, y, yaw_deg) of base_link in the Z-up map frame, or None.

        The pose VPS returns describes the CAMERA; this applies the mount chain
        so the answer describes the robot.

        Localizes: one capture, one query. If you already hold a Pose, call
        camera_pose_to_base(pose.matrix) instead of paying for a second one.
        """
        pose = self.localize(**kwargs)  # type: ignore[arg-type]
        if not pose.found:
            return None
        T = camera_pose_to_base(pose.matrix)
        return float(T[0, 3]), float(T[1, 3]), math.degrees(math.atan2(T[1, 0], T[0, 0]))

    # -- telemetry ---------------------------------------------------------

    def subscribe_odometry(self, callback) -> object:
        """Odometry poses as (x, y, yaw_rad) in the ROBOT's own frame.

        Not the map frame: odometry starts wherever the robot booted. Compose it
        onto a VPS fix to get a map pose -- compose_map_from_odom() below does
        exactly that, and shows how.

        The callback runs on the transport's loop thread. Copy and return.
        """

        def on_message(message: dict) -> None:
            pose = (message.get("data") or {}).get("pose") or {}
            position = pose.get("position") or {}
            orientation = pose.get("orientation") or {}
            x, y, z, w = (float(orientation.get(k, 0.0)) for k in ("x", "y", "z", "w"))
            yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
            callback((float(position.get("x", 0.0)), float(position.get("y", 0.0)), yaw))

        return self.transport.subscribe(RTC_TOPIC["ROBOTODOM"], on_message)


def compose_map_from_odom(anchor_map, anchor_odom, odom_now):
    """Carry a map pose forward with an odometry delta. Each arg is (x, y, yaw).

    Kept deliberately identical to the navigator's own composition: if the
    viewer composed poses even slightly differently, the drawn track would
    diverge from the one the robot believed it was on, and the picture would
    quietly misrepresent the run.
    """
    mx, my, myaw = anchor_map
    ox0, oy0, oyaw0 = anchor_odom
    ox, oy, oyaw = odom_now
    dx, dy = ox - ox0, oy - oy0
    c, s = math.cos(-oyaw0), math.sin(-oyaw0)
    lx, ly = c * dx - s * dy, s * dx + c * dy
    dyaw = math.atan2(math.sin(oyaw - oyaw0), math.cos(oyaw - oyaw0))
    cm, sm = math.cos(myaw), math.sin(myaw)
    return (
        mx + cm * lx - sm * ly,
        my + sm * lx + cm * ly,
        math.atan2(math.sin(myaw + dyaw), math.cos(myaw + dyaw)),
    )


def localize(
    settings: Go2Settings | None = None,
    vps_settings: VPSSettings | None = None,
    **kwargs: object,
) -> Pose:
    """One-shot: connect, localize, disconnect.

        from multiset.unitree.go2 import localize
        pose = localize()

    Convenient for a script; wasteful in a loop, where the connection should be
    held open with `with Go2.from_env() as dog:` instead. For the device-agnostic
    version that takes an already-connected source, see multiset.vps.localize.
    """
    with Go2(settings, vps_settings) as dog:
        return dog.localize(**kwargs)  # type: ignore[arg-type]


__all__ = [
    "CALIBRATIONS",
    "compose_map_from_odom",
    "FRONT",
    "GO2_FRONT_720P",
    "GO2_MOUNT",
    "HEIGHT",
    "WIDTH",
    "YUP_TO_ZUP",
    "Go2",
    "camera_pose_to_base",
    "localize",
]
