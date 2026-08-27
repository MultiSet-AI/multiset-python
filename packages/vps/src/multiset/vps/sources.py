"""The contract a frame source implements.

Anything that can hand over a rectified image with the intrinsics describing it
can be localized.

    class MyCamera:
        def capture(self) -> Frame:
            ...

    pose = localize(MyCamera())
"""

from __future__ import annotations

from typing import NamedTuple, Protocol, runtime_checkable

import numpy as np

from .intrinsics import PinholeIntrinsics


class Frame(NamedTuple):
    """A rectified image and the intrinsics describing THAT image.

    The pairing is the point: a rectified image sent with the raw focal length
    is a ~10% error on every bearing that the server answers poseFound=true to.
    """

    image: np.ndarray
    intrinsics: PinholeIntrinsics


@runtime_checkable
class FrameSource(Protocol):
    """One method, implemented by anything that can be localized."""

    def capture(self) -> Frame:
        """One rectified frame and its intrinsics.

        May block. Raises CameraError, or FrameTimeout, when no frame arrives.
        """
        ...


__all__ = ["Frame", "FrameSource"]
