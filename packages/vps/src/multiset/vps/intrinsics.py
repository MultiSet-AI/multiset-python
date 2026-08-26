"""Fisheye in, pinhole out -- with the intrinsics that describe the result.

Most cameras worth localizing with are wide, and VPS -- like any pinhole pose
solver -- expects a rectified image described by pinhole intrinsics. A raw frame
means nothing geometrically until it is remapped.

THE ONE THING TO GET RIGHT
--------------------------
There are two sets of numbers here and they are NOT interchangeable:

  RAW FISHEYE           describes the distorted sensor image. Consumed by
  (FisheyeCalibration)  cv2.fisheye.*. Never sent to a pose solver.
  RECTIFIED PINHOLE     describes the image remap produces. THIS is what VPS
  (PinholeIntrinsics)   receives, with distortion = none.

Rectification shortens the focal length, so the two differ by roughly 10%.
Sending raw K with an undistorted image is a ~10% error on every bearing, and
the server still answers poseFound=true. Rectifier returns the image and its
intrinsics as a pair so the two cannot be separated.

The calibration values themselves live in the DEVICE packages, next to the
hardware they describe. This module is the machinery only.
"""

from __future__ import annotations

import functools
import math
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from .errors import CalibrationError


@dataclass(frozen=True)
class FisheyeCalibration:
    """Raw equidistant-fisheye parameters for one sensor at one resolution.

    Do NOT mix values between calibrations. D is fitted jointly with the
    principal point, and a hybrid of one fit's focal length with another's
    centre measures worse than either. The resolution is part of the
    calibration for the same reason: these coefficients describe the sensor as
    it reads out, and applying them to a resized frame yields a plausible
    picture with wrong geometry.
    """

    name: str
    fx: float
    fy: float
    cx: float
    cy: float
    k: tuple[float, float, float, float]
    width: int
    height: int
    note: str = ""

    @property
    def K(self) -> np.ndarray:
        return np.array(
            [[self.fx, 0.0, self.cx], [0.0, self.fy, self.cy], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )

    @property
    def D(self) -> np.ndarray:
        return np.array(self.k, dtype=np.float64).reshape(4, 1)

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)


@dataclass(frozen=True)
class PinholeIntrinsics:
    """Describes the UNDISTORTED image -- what a pose solver must be told.

    Distortion is zero by construction: the remap removed it.
    """

    fx: float
    fy: float
    px: float
    py: float
    width: int
    height: int
    source: str = "unknown"

    @property
    def hfov_deg(self) -> float:
        return float(np.degrees(2 * math.atan(self.width / (2 * self.fx))))

    @property
    def vfov_deg(self) -> float:
        return float(np.degrees(2 * math.atan(self.height / (2 * self.fy))))

    def scaled(self, factor: float, width: int, height: int) -> PinholeIntrinsics:
        """Intrinsics for the same view resized by `factor`.

        Resizing an image without scaling its intrinsics with it is the same
        class of silent error as swapping raw for rectified, so the client that
        downsizes an oversized query calls this rather than editing fields.
        """
        return PinholeIntrinsics(
            fx=self.fx * factor,
            fy=self.fy * factor,
            px=self.px * factor,
            py=self.py * factor,
            width=width,
            height=height,
            source=self.source,
        )

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data.update(
            model="pinhole",
            distortion="none",
            hfov_deg=round(self.hfov_deg, 2),
            vfov_deg=round(self.vfov_deg, 2),
        )
        return data

    def __str__(self) -> str:
        return (
            f"fx={self.fx:.4f} fy={self.fy:.4f} px={self.px:.4f} py={self.py:.4f} "
            f"({self.hfov_deg:.1f}x{self.vfov_deg:.1f} deg FOV)"
        )


@functools.lru_cache(maxsize=8)
def _rectify_maps(calibration: FisheyeCalibration):
    """(map1, map2, rectified intrinsics), cached per calibration.

    Building the maps costs milliseconds and depends on nothing but the
    calibration, so a capture loop at 14 fps would otherwise rebuild identical
    tables fourteen times a second. Cacheable because FisheyeCalibration is
    frozen and hashable.

    balance=0.0 keeps only pixels backed by real source data, so the result has
    no black wedges in the corners. That crops the field of view slightly, which
    is exactly why the rectified focal length is shorter than the raw one -- and
    why the two must never be swapped.
    """
    size = calibration.size
    new_K = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
        calibration.K, calibration.D, size, np.eye(3), balance=0.0
    )
    m1, m2 = cv2.fisheye.initUndistortRectifyMap(
        calibration.K, calibration.D, np.eye(3), new_K, size, cv2.CV_16SC2
    )
    return (
        m1,
        m2,
        PinholeIntrinsics(
            fx=float(new_K[0, 0]),
            fy=float(new_K[1, 1]),
            px=float(new_K[0, 2]),
            py=float(new_K[1, 2]),
            width=calibration.width,
            height=calibration.height,
            source=calibration.name,
        ),
    )


class Rectifier:
    """A calibration plus its cached remap tables.

    Device packages build one of these from their own calibration and expose it;
    users rarely construct one directly.
    """

    def __init__(self, calibration: FisheyeCalibration) -> None:
        self.calibration = calibration

    @property
    def intrinsics(self) -> PinholeIntrinsics:
        """The rectified intrinsics alone, without undistorting anything."""
        return _rectify_maps(self.calibration)[2]

    def undistort(self, image: np.ndarray) -> tuple[np.ndarray, PinholeIntrinsics]:
        """Fisheye frame -> (pinhole frame, its intrinsics). Pure, in-memory.

        Raises CalibrationError on any frame that is not the calibration's own
        resolution: rescaling the image would need the intrinsics rescaled with
        it, and nothing downstream would complain if it were not.
        """
        height, width = image.shape[:2]
        if (width, height) != self.calibration.size:
            raise CalibrationError(
                f"expected a {self.calibration.width}x{self.calibration.height} frame, "
                f"got {width}x{height}. Calibration {self.calibration.name!r} describes "
                f"that sensor at that resolution only."
            )
        m1, m2, intrinsics = _rectify_maps(self.calibration)
        return cv2.remap(image, m1, m2, interpolation=cv2.INTER_LINEAR), intrinsics

    def __repr__(self) -> str:
        return f"Rectifier({self.calibration.name!r})"


def undistort(
    image: np.ndarray, calibration: FisheyeCalibration
) -> tuple[np.ndarray, PinholeIntrinsics]:
    """One-shot rectification. Equivalent to Rectifier(calibration).undistort(image)."""
    return Rectifier(calibration).undistort(image)


def intrinsics(calibration: FisheyeCalibration) -> PinholeIntrinsics:
    """The rectified intrinsics for a calibration, without undistorting anything."""
    return _rectify_maps(calibration)[2]


__all__ = [
    "FisheyeCalibration",
    "PinholeIntrinsics",
    "Rectifier",
    "intrinsics",
    "undistort",
]
