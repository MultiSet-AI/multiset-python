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
import time
from collections import deque

import cv2
import numpy as np
from multiset.vps import CameraError, Panorama

from .config import Insta360Settings
from .errors import NotPanoramic, RemoteCameraError

log = logging.getLogger(__name__)

_JPEG_START, _JPEG_END = b"\xff\xd8", b"\xff\xd9"

_TAIL_ROWS = 8

#: Seconds discarded on open: the camera's yaw origin is still settling, and a
#: heading read before it locks can be 165 degrees out at full confidence.
DEFAULT_WARMUP = 1.5

#: Clean frames measure 5.1-5.4, a visible tear 22.7.
_TEAR_RATIO = 12.0

#: Older than this and the stream has stalled; a stale frame localizes where
#: the robot used to be.
MAX_FRAME_AGE = 5.0

_MAX_BUFFER = 32 << 20
_KEEP_FRAMES = 4
_READ_TIMEOUT = 3.0


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
        warmup: float = DEFAULT_WARMUP,
        max_frame_age: float = MAX_FRAME_AGE,
    ) -> None:
        """`host` is anything ssh accepts. `command` replaces the whole argv,
        which is how the tests drive this without a robot. `warmup=0` takes the
        first frame that arrives."""
        self.host = host
        self.max_frame_age = max_frame_age
        argv = command or [
            "ssh",
            "-o",
            "BatchMode=yes",
            host,
            _remote_pipeline(device, width, height, fps),
        ]
        self.process = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
        )
        self._frames: deque[tuple[float, bytes]] = deque(maxlen=_KEEP_FRAMES)
        self._errors: deque[str] = deque(maxlen=8)
        self._dropped = 0
        self._running = True
        self._arrived = threading.Event()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

        if not self._await_first_frame(connect_timeout):
            reason = self.failure_reason()
            self.close()
            raise RemoteCameraError(
                f"no frames from {host}. Check, in order: the camera is in Webcam "
                f"mode + 360 view; {device} exists on the robot; ffmpeg or "
                f"gst-launch-1.0 is on its PATH; and `ssh {host} true` succeeds "
                f"without a password." + (f"\nssh said: {reason}" if reason else "")
            )
        frame = self.read()
        frame_height, frame_width = frame.shape[:2]
        if frame_height == 0 or abs(frame_width / frame_height - 2.0) > 0.1:
            self.close()
            raise NotPanoramic(host, frame_width, frame_height)
        self.resolution = (frame_width, frame_height)
        if warmup > 0:
            time.sleep(warmup)
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
            warmup=settings.warmup,
        )

    def failure_reason(self) -> str:
        """What ssh or the remote command wrote to stderr, if anything."""
        return " / ".join(self._errors)

    def _await_first_frame(self, timeout: float) -> bool:
        """Give up early when the session is already dead -- a rejected key
        should not cost the full timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._arrived.wait(0.1):
                return True
            if self.process.poll() is not None:
                return False
        return False

    def _drain_stderr(self) -> None:
        pipe = self.process.stderr
        if pipe is None:
            return
        for line in iter(pipe.readline, b""):
            text = line.decode("utf-8", "replace").strip()
            if text:
                self._errors.append(text)
                log.debug("insta360: %s: %s", self.host, text)

    def _pump(self) -> None:
        """Split the MJPEG stream into frames, keeping only the newest few.

        Frames are stored undecoded: at 8 fps and 22 ms a decode, decoding
        every one to answer a query every few seconds burns a quarter of a core
        for nothing. `read()` decodes what it actually needs.
        """
        stdout = self.process.stdout
        assert stdout is not None
        buffer = bytearray()
        while self._running:
            chunk = stdout.read(65536)
            if not chunk:
                break
            buffer += chunk
            if len(buffer) > _MAX_BUFFER:
                buffer.clear()
                continue
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
                # a second SOI means this slice ran on into the next frame
                if jpeg.find(_JPEG_START, 2) >= 0:
                    self._dropped += 1
                    continue
                self._frames.append((time.monotonic(), jpeg))
                self._arrived.set()

    def read(self) -> np.ndarray:
        """The most recent undamaged frame (BGR).

        A damaged frame decodes fine and localizes confidently and wrongly, so
        each is checked and the bad ones dropped. Blocks briefly while they are,
        since the opening frames of a stream are often torn.
        """
        deadline = time.monotonic() + _READ_TIMEOUT
        seen: set[float] = set()
        while True:
            if not self._frames or (not self._thread.is_alive() and self._running):
                raise CameraError(
                    f"the video stream from {self.host} ended. {self.failure_reason()}".strip()
                )
            age = time.monotonic() - self._frames[-1][0]
            if age > self.max_frame_age:
                raise CameraError(
                    f"no frame from {self.host} for {age:.0f}s -- the stream has stalled"
                )
            for stamp, jpeg in reversed(list(self._frames)):
                if stamp in seen:
                    continue
                seen.add(stamp)
                frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                if frame is None or _tail_is_filler(frame) or _is_torn(frame):
                    self._dropped += 1
                    continue
                return frame
            if time.monotonic() > deadline:
                raise CameraError(
                    f"every frame from {self.host} in the last {_READ_TIMEOUT:.0f}s "
                    f"arrived damaged -- the link is losing bytes"
                )
            time.sleep(0.05)

    def capture_panorama(self) -> Panorama:
        """One equirectangular frame. This is the `PanoramaSource` contract."""
        return Panorama(self.read())

    def close(self) -> None:
        """Close the SSH session. Safe to call twice; the robot keeps nothing."""
        self._running = False
        process = getattr(self, "process", None)
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()

    def __enter__(self) -> SSHCamera:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _tail_is_filler(frame: np.ndarray) -> bool:
    """Whether the last rows are the decoder's fill -- flat grey, or green --
    rather than picture."""
    tail = frame[-_TAIL_ROWS:].astype(np.int16)
    if bool((tail.reshape(_TAIL_ROWS, -1).std(axis=1) < 1.0).all()):
        return True
    _, green, red = tail.reshape(_TAIL_ROWS, -1, 3).mean(axis=1).T
    return bool((green - red).mean() > 50)


def _is_torn(frame: np.ndarray) -> bool:
    """Whether a seam splits the frame where bytes were lost.

    Rows either side of a tear come from different parts of the picture, so the
    step between them dwarfs the frame's own median.
    """
    rows = frame[:, ::8].astype(np.int16)
    step = np.abs(np.diff(rows, axis=0)).reshape(rows.shape[0] - 1, -1).mean(axis=1)
    median = float(np.median(step))
    return median > 0.0 and float(step.max()) / median > _TEAR_RATIO


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


__all__ = ["DEFAULT_WARMUP", "MAX_FRAME_AGE", "SSHCamera"]
