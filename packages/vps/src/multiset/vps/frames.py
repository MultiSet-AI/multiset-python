"""Frame conventions. Each of these is silent when wrong -- you get a
plausible result, not an error.

1. VPS returns Y-up; maps and viewers are Z-up.                -> YUP_TO_ZUP
2. VPS returns an ARKit camera frame (+Y up, -Z forward); mount
   chains are written in OpenCV optical (+Y down, +Z forward). -> CAM_TO_OPTICAL
3. A VPS pose describes the CAMERA, not what carries it.       -> Mount
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Rx(+90): right-handed Y-up -> Z-up.
YUP_TO_ZUP = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
)

# ARKit (+Y up, -Z forward) -> OpenCV optical (+Y down, +Z forward): 180 deg
# about X. A CAMERA-frame conversion, so it applies before the mount inverse.
CAM_TO_OPTICAL = np.diag([1.0, -1.0, -1.0, 1.0])


def quaternion_matrix(x: float, y: float, z: float, w: float) -> np.ndarray:
    """A 4x4 rotation from a quaternion, normalising as it goes."""
    n = x * x + y * y + z * z + w * w
    s = 0.0 if n == 0 else 2.0 / n
    T = np.eye(4)
    T[:3, :3] = [
        [1 - s * (y * y + z * z), s * (x * y - z * w), s * (x * z + y * w)],
        [s * (x * y + z * w), 1 - s * (x * x + z * z), s * (y * z - x * w)],
        [s * (x * z - y * w), s * (y * z + x * w), 1 - s * (x * x + y * y)],
    ]
    return T


@dataclass(frozen=True)
class Mount:
    """Where a camera sits on its device: origin -> camera optical frame."""

    name: str
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)  # x, y, z, w
    note: str = ""

    @property
    def matrix(self) -> np.ndarray:
        """4x4 device-origin -> optical frame."""
        T = quaternion_matrix(*self.rotation)
        T[:3, 3] = self.translation
        return T


# The camera is the origin, so there is nothing to undo.
HANDHELD = Mount(name="handheld", note="the camera is the origin")


def camera_pose_to_origin(pose_matrix: np.ndarray, mount: Mount) -> np.ndarray:
    """A VPS camera pose -> the device's own origin, in the Z-up map frame.

    Both conversions, in order: YUP_TO_ZUP into the map frame, then the mount
    chain from the lens back to the origin.
    """
    return (YUP_TO_ZUP @ pose_matrix) @ CAM_TO_OPTICAL @ np.linalg.inv(mount.matrix)


__all__ = [
    "CAM_TO_OPTICAL",
    "HANDHELD",
    "YUP_TO_ZUP",
    "Mount",
    "camera_pose_to_origin",
    "quaternion_matrix",
]
