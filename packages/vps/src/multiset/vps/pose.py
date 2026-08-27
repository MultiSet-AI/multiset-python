"""The result type: what VPS answered about one frame.

One type for every frame source, so poses compose without conversion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .frames import quaternion_matrix


@dataclass(frozen=True)
class Pose:
    """A localization result in the VPS map frame.

    Y-up whatever handedness was requested, and it describes the CAMERA, not
    whatever the camera is mounted on. See multiset.vps.frames to convert.
    """

    found: bool
    position: np.ndarray  # (3,) xyz
    rotation: np.ndarray  # (4,) quaternion x, y, z, w
    confidence: float
    response_ms: float
    map_codes: tuple[str, ...] = ()
    # A code is what you configure; an id is what the service matched.
    map_ids: tuple[str, ...] = ()
    raw: dict = field(repr=False, default_factory=dict)

    @classmethod
    def from_response(cls, data: dict, *, position_key: str | None = None) -> Pose:
        """Build a Pose from one API reply.

        Endpoints disagree on the envelope: /vps/map/query puts `position` and
        `rotation` at the top level, multi-image-query nests them under
        `estimatedPose`. `position_key` names that sub-object; None reads the
        top level.
        """
        source = (data.get(position_key) or {}) if position_key else data
        position = source.get("position") or {}
        rotation = source.get("rotation") or {}
        return cls(
            found=bool(data.get("poseFound")),
            position=np.array(
                [position.get("x", 0.0), position.get("y", 0.0), position.get("z", 0.0)],
                dtype=float,
            ),
            rotation=np.array(
                [
                    rotation.get("x", 0.0),
                    rotation.get("y", 0.0),
                    rotation.get("z", 0.0),
                    rotation.get("w", 1.0),
                ],
                dtype=float,
            ),
            confidence=float(data.get("confidence", 0.0)),
            response_ms=float(data.get("responseTime", 0.0)),
            map_codes=tuple(data.get("mapCodes") or ()),
            map_ids=tuple(data.get("mapIds") or ()),
            raw=data,
        )

    @property
    def x(self) -> float:
        return float(self.position[0])

    @property
    def y(self) -> float:
        return float(self.position[1])

    @property
    def z(self) -> float:
        return float(self.position[2])

    @property
    def matrix(self) -> np.ndarray:
        """4x4 camera pose in the VPS map frame."""
        T = quaternion_matrix(*self.rotation)
        T[:3, 3] = self.position
        return T

    @property
    def yaw_deg(self) -> float:
        """Heading in the map frame, degrees."""
        T = self.matrix
        return math.degrees(math.atan2(T[1, 0], T[0, 0]))

    def __bool__(self) -> bool:
        return self.found

    def __str__(self) -> str:
        if not self.found:
            return f"no pose ({self.response_ms:.0f} ms)"
        return (
            f"({self.x:+.3f}, {self.y:+.3f}, {self.z:+.3f}) "
            f"conf {self.confidence:.3f}  {self.response_ms:.0f} ms"
        )


__all__ = ["Pose"]
