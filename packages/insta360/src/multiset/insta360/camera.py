"""An Insta360 X-series camera on this machine's USB, in webcam mode.

The camera stitches; we only read. In Webcam mode + 360 view it is a plain UVC
device delivering 2:1 frames, so there is no Insta360 SDK here. Any model works
-- what is required is a UVC device whose frames are 2:1.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import cv2
import numpy as np
from multiset.vps import CameraError, Panorama

from .errors import CameraNotFound, NotPanoramic

log = logging.getLogger(__name__)


@contextmanager
def _opencv_quiet() -> Iterator[None]:
    """Silence OpenCV while probing. A miss is normal and it warns loudly.

    Two layers: the log level, and fd 2 -- the C++ backends write there
    directly, ignoring the level. Both restored, including on an exception.
    """
    previous_level: int | None = None
    try:
        previous_level = cv2.utils.logging.getLogLevel()
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
    except (AttributeError, cv2.error):  # older opencv, or a build without it
        previous_level = None

    saved_stderr = None
    devnull = None
    try:
        saved_stderr = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 2)
    except OSError:  # no usable stderr to redirect; the log level may still help
        saved_stderr = None

    try:
        yield
    finally:
        if saved_stderr is not None:
            os.dup2(saved_stderr, 2)
            os.close(saved_stderr)
        if devnull is not None:
            os.close(devnull)
        if previous_level is not None:
            cv2.utils.logging.setLogLevel(previous_level)


#: A request, not an assumption: UVC negotiates, and whatever arrives is used.
DEFAULT_WIDTH, DEFAULT_HEIGHT = 2880, 1440

#: Reads discarded after asking for a resolution. The first one back is from
#: the old mode, or empty, so judging a camera on it rejects a working one.
_SETTLE_READS = 4


def _settled_frame(capture: cv2.VideoCapture, width: int, height: int) -> np.ndarray | None:
    """Ask for a resolution and return a frame actually taken at it."""
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    frame = None
    for _ in range(_SETTLE_READS):
        ok, latest = capture.read()
        if ok and latest is not None:
            frame = latest
    return frame


class UsbCamera:
    """Live equirectangular frames from an Insta360 on this machine's USB.

        with UsbCamera() as cam:
            pose = localize(cam)

    A `multiset.vps.PanoramaSource`, like `SSHCamera`. Discovery matches an
    Insta360 by name on Linux, else the first 2:1 device; `device=` skips it.
    """

    def __init__(
        self,
        device: int | str | None = None,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
    ) -> None:
        resolved = self._discover() if device is None else device
        if resolved is None:
            raise CameraNotFound
        self.device = resolved
        self.capture_device = cv2.VideoCapture(resolved)
        frame = _settled_frame(self.capture_device, width, height)
        if frame is None:
            self.close()
            raise CameraError(
                f"device {resolved} opened but produced no frames. If the camera "
                f"screen is still showing the mode prompt, choose Webcam mode."
            )
        frame_height, frame_width = frame.shape[:2]
        if frame_height == 0 or abs(frame_width / frame_height - 2.0) > 0.1:
            self.close()
            raise NotPanoramic(f"device {resolved}", frame_width, frame_height)
        self.resolution = (frame_width, frame_height)
        log.info("insta360: %s delivering %dx%d equirect", resolved, *self.resolution)

    @staticmethod
    def _discover(width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT) -> int | str | None:
        """An Insta360 by name, else the first 2:1 device.

        Probes at the panoramic resolution, not the default one: an X5 offers
        both 1920x1080 and 2880x1440, and only the second is equirect, so a
        probe that never asks sees a 16:9 device and walks past the camera.

        Never probes blindly: OpenCV warns loudly per miss, which buries the
        one message that matters.
        """
        linux_devices = sorted(Path("/sys/class/video4linux").glob("video*/name"))
        if linux_devices:
            for meta in linux_devices:
                try:
                    name = meta.read_text()
                except OSError:
                    continue
                if "insta360" in name.lower():
                    return "/dev/" + meta.parent.name
            # only devices that exist, never blind indices
            candidates: list[int | str] = ["/dev/" + m.parent.name for m in linux_devices]
        elif Path("/sys/class/video4linux").is_dir():
            return None  # Linux, directory empty: definitely no camera
        else:
            candidates = list(range(6))  # no listing available, so guess

        with _opencv_quiet():
            for candidate in candidates:
                probe = cv2.VideoCapture(candidate)
                try:
                    frame = _settled_frame(probe, width, height)
                finally:
                    probe.release()
                if frame is not None and frame.shape[0]:
                    frame_height, frame_width = frame.shape[:2]
                    if abs(frame_width / frame_height - 2.0) < 0.1:
                        return candidate
        return None

    def read(self) -> np.ndarray:
        """The latest frame, BGR. Grabs twice: a buffered frame is a stale pose."""
        self.capture_device.grab()
        ok, frame = self.capture_device.read()
        if not ok or frame is None:
            raise CameraError(f"device {self.device} stopped delivering frames")
        return frame

    def capture_panorama(self) -> Panorama:
        """One equirectangular frame. This is the `PanoramaSource` contract."""
        return Panorama(self.read())

    def close(self) -> None:
        """Release the device. Safe to call twice."""
        device = getattr(self, "capture_device", None)
        if device is not None:
            device.release()

    def __enter__(self) -> UsbCamera:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


__all__ = ["DEFAULT_HEIGHT", "DEFAULT_WIDTH", "UsbCamera"]
