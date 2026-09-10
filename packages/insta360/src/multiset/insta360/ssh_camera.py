"""A camera on a robot, read over SSH. Nothing is installed on the robot.

It needs only its stock sshd and the ffmpeg or GStreamer already on its image;
the session itself carries the video.

    with SSHCamera("unitree@192.168.123.18") as cam:
        pose = localize(cam)

Key auth only, so run `ssh-copy-id <host>` once first.
"""

from __future__ import annotations

import logging
import subprocess
import threading

import cv2
import numpy as np
from multiset.vps import CameraError, Panorama

from .config import Insta360Settings
from .errors import NotPanoramic, RemoteCameraError

log = logging.getLogger(__name__)

_JPEG_START, _JPEG_END = b"\xff\xd8", b"\xff\xd9"


class SSHCamera:
    """Equirect frames from a camera on another machine, over SSH.

    Same `PanoramaSource` contract as `UsbCamera`: swapping them is the only
    change needed to move from a laptop to a robot.
    """

    def __init__(
        self,
        host: str,
        device: str = "/dev/video0",
        width: int = 2880,
        height: int = 1440,
        fps: int = 5,
        command: list[str] | None = None,
        connect_timeout: float = 25.0,
    ) -> None:
        """`host` is anything ssh accepts. `command` replaces the whole argv,
        which is how the tests drive this without a robot."""
        self.host = host
        argv = command or [
            "ssh",
            "-o",
            "BatchMode=yes",
            host,
            _remote_pipeline(device, width, height, fps),
        ]
        self.process = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0
        )
        self._latest: np.ndarray | None = None
        self._running = True
        self._first_frame = threading.Event()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

        if not self._first_frame.wait(connect_timeout):
            self.close()
            raise RemoteCameraError(
                f"no frames from {host} within {connect_timeout:.0f}s. Check, in "
                f"order: the camera is in Webcam mode + 360 view; {device} exists "
                f"on the robot; ffmpeg or gst-launch-1.0 is on its PATH; and "
                f"`ssh {host} true` succeeds without a password."
            )
        frame = self._latest
        assert frame is not None
        frame_height, frame_width = frame.shape[:2]
        if frame_height == 0 or abs(frame_width / frame_height - 2.0) > 0.1:
            self.close()
            raise NotPanoramic(host, frame_width, frame_height)
        self.resolution = (frame_width, frame_height)
        log.info("insta360: %s delivering %dx%d equirect", host, *self.resolution)

    @classmethod
    def from_env(cls, env_file: str | None = None, **overrides: object) -> SSHCamera:
        """Build from .env. The counterpart of `Go2.from_env()`."""
        settings = Insta360Settings.from_env(env_file, **overrides)
        return cls(
            settings.require_ssh_host(),
            device=settings.device,
            width=settings.width,
            height=settings.height,
            fps=settings.fps,
            connect_timeout=settings.connect_timeout,
        )

    def _pump(self) -> None:
        """Split the MJPEG stream into frames, keeping only the newest.

        A query takes seconds, so a backlog means localizing where the robot
        used to be.
        """
        stdout = self.process.stdout
        assert stdout is not None
        buffer = bytearray()
        while self._running:
            chunk = stdout.read(65536)
            if not chunk:
                break
            buffer += chunk
            while True:
                start = buffer.find(_JPEG_START)
                if start < 0:
                    buffer.clear()
                    break
                end = buffer.find(_JPEG_END, start + 2)
                if end < 0:
                    del buffer[:start]  # keep the partial frame, drop the junk
                    break
                jpeg = bytes(buffer[start : end + 2])
                del buffer[: end + 2]
                frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    self._latest = frame
                    self._first_frame.set()

    def read(self) -> np.ndarray:
        """The most recent frame (BGR)."""
        if self._latest is None or (not self._thread.is_alive() and self._running):
            raise CameraError(f"the video stream from {self.host} ended")
        return self._latest

    def capture_panorama(self) -> Panorama:
        """One equirectangular frame. This is the `PanoramaSource` contract."""
        return Panorama(self.read())

    def close(self) -> None:
        """Close the SSH session. Safe to call twice; the robot keeps nothing."""
        self._running = False
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None:
            process.terminate()

    def __enter__(self) -> SSHCamera:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _remote_pipeline(device: str, width: int, height: int, fps: int) -> str:
    """MJPEG to stdout, whatever the robot has.

    Four fallbacks, best first -- no re-encode, then re-encode, each in ffmpeg
    and GStreamer flavours -- because robot images differ in what they ship.
    """
    ffmpeg_copy = (
        f"ffmpeg -loglevel error -f v4l2 -input_format mjpeg "
        f"-video_size {width}x{height} -i {device} -c:v copy -f mjpeg -"
    )
    ffmpeg_encode = (
        f"ffmpeg -loglevel error -f v4l2 -video_size {width}x{height} "
        f"-i {device} -vf fps={fps} -q:v 6 -f mjpeg -"
    )
    gst_copy = (
        f"gst-launch-1.0 -q v4l2src device={device} ! "
        f"image/jpeg,width={width},height={height} ! fdsink fd=1"
    )
    gst_encode = (
        f"gst-launch-1.0 -q v4l2src device={device} ! "
        f"video/x-raw,width={width},height={height} ! videorate ! "
        f"video/x-raw,framerate={fps}/1 ! videoconvert ! "
        f"jpegenc quality=70 ! fdsink fd=1"
    )
    return f"{ffmpeg_copy} || {ffmpeg_encode} || {gst_copy} || {gst_encode}"


__all__ = ["SSHCamera"]
