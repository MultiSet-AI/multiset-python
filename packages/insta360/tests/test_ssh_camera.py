"""The robot path, without a robot.

SSHCamera takes a `command` override, so a local script standing in for the
SSH session exercises the real MJPEG parsing, threading and 2:1 check.
"""

from __future__ import annotations

import sys
import time

import pytest
from multiset.insta360 import NotPanoramic, RemoteCameraError, SSHCamera
from multiset.vps import CameraError, PanoramaSource

# a producer that writes N equirect JPEGs to stdout and stops, like the remote
# ffmpeg pipeline does
PRODUCER = """
import sys, numpy as np, cv2
w, h, n = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
rng = np.random.default_rng(0)
frame = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
ok, buf = cv2.imencode('.jpg', frame)
for _ in range(n):
    sys.stdout.buffer.write(buf.tobytes())
sys.stdout.buffer.flush()
"""


def producer(width=640, height=320, frames=3, script=PRODUCER):
    return [sys.executable, "-c", script, str(width), str(height), str(frames)]


# these producers stop after N frames, so the default warmup outlives the stream
NO_WARMUP = {"warmup": 0.0}

# keeps writing until killed, the way the remote pipeline does
STREAMER = """
import sys, time, numpy as np, cv2
w, h = int(sys.argv[1]), int(sys.argv[2])
rng = np.random.default_rng(0)
ok, buf = cv2.imencode('.jpg', rng.integers(0, 255, (h, w, 3), dtype=np.uint8))
while True:
    sys.stdout.buffer.write(buf.tobytes())
    sys.stdout.buffer.flush()
    time.sleep(0.05)
"""


def streamer(width=640, height=320):
    return [sys.executable, "-c", STREAMER, str(width), str(height)]


# a few frames, then the session stays up and goes quiet
STALLER = PRODUCER + "\nimport time; time.sleep(30)\n"


def test_it_parses_frames_out_of_the_mjpeg_stream():
    with SSHCamera("fake@host", command=producer(), **NO_WARMUP) as cam:
        assert cam.resolution == (640, 320)
        frame = cam.read()
        assert frame.shape == (320, 640, 3)


def test_it_satisfies_the_panorama_contract():
    with SSHCamera("fake@host", command=producer(), **NO_WARMUP) as cam:
        assert isinstance(cam, PanoramaSource)
        (image,) = cam.capture_panorama()
        assert image.shape == (320, 640, 3)


def test_a_single_lens_stream_is_rejected_with_the_reason():
    """Not 2:1 means single-lens mode -- say so, do not upload."""
    with pytest.raises(NotPanoramic, match="360 view"):
        SSHCamera("fake@host", command=producer(640, 480), **NO_WARMUP)


def test_a_silent_host_fails_with_something_actionable():
    quiet = [sys.executable, "-c", "import time; time.sleep(30)"]
    with pytest.raises(RemoteCameraError, match="ffmpeg or gst-launch"):
        SSHCamera("fake@host", command=quiet, connect_timeout=1.0)


def test_junk_before_the_first_marker_is_skipped():
    """A remote shell may print a banner before the video starts."""
    noisy = "import sys\nsys.stdout.buffer.write(b'Welcome to Ubuntu 20.04\\n')\n" + PRODUCER
    with SSHCamera("fake@host", command=producer(script=noisy), **NO_WARMUP) as cam:
        assert cam.resolution == (640, 320)


def test_closing_twice_is_harmless():
    cam = SSHCamera("fake@host", command=producer(), **NO_WARMUP)
    cam.close()
    cam.close()


def test_the_remote_pipeline_offers_four_fallbacks():
    """Robot images differ in shipping ffmpeg or GStreamer."""
    from multiset.insta360.ssh_camera import _remote_pipeline

    pipeline = _remote_pipeline("/dev/video0", 2880, 1440, 5)
    assert pipeline.count("||") == 3
    assert "ffmpeg" in pipeline and "gst-launch-1.0" in pipeline
    assert "-c:v copy" in pipeline, "the no-re-encode path should be tried first"
    assert pipeline.index("-c:v copy") < pipeline.index("gst-launch-1.0")
    assert "2880x1440" in pipeline


def test_warmup_discards_the_opening_frames():
    """The camera's yaw origin is still settling there."""
    import time

    from multiset.insta360.ssh_camera import DEFAULT_WARMUP

    assert DEFAULT_WARMUP > 0
    started = time.monotonic()
    with SSHCamera("fake@host", command=streamer(), warmup=0.4) as cam:
        elapsed = time.monotonic() - started
        assert elapsed >= 0.4, "the constructor returned before the warmup elapsed"
        assert cam.read().shape == (320, 640, 3)


def test_a_dead_session_fails_without_waiting_out_the_timeout():
    """A rejected key should not cost the full connect timeout."""
    import time

    refused = [sys.executable, "-c", "import sys; sys.stderr.write('Permission denied\\n')"]
    started = time.monotonic()
    with pytest.raises(RemoteCameraError, match="Permission denied"):
        SSHCamera("fake@host", command=refused, connect_timeout=20.0)
    assert time.monotonic() - started < 5.0


def test_a_stalled_stream_is_refused_rather_than_served_stale():
    cam = SSHCamera(
        "fake@host", command=producer(script=STALLER), max_frame_age=0.2, **NO_WARMUP
    )
    time.sleep(0.4)
    with pytest.raises(CameraError, match="stalled"):
        cam.read()
    cam.close()
