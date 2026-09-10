"""The robot path, without a robot.

SSHCamera takes a `command` override, so a local script standing in for the
SSH session exercises the real MJPEG parsing, threading and 2:1 check.
"""

from __future__ import annotations

import sys

import pytest
from multiset.insta360 import NotPanoramic, RemoteCameraError, SSHCamera
from multiset.vps import PanoramaSource

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


def test_it_parses_frames_out_of_the_mjpeg_stream():
    with SSHCamera("fake@host", command=producer()) as cam:
        assert cam.resolution == (640, 320)
        frame = cam.read()
        assert frame.shape == (320, 640, 3)


def test_it_satisfies_the_panorama_contract():
    with SSHCamera("fake@host", command=producer()) as cam:
        assert isinstance(cam, PanoramaSource)
        (image,) = cam.capture_panorama()
        assert image.shape == (320, 640, 3)


def test_a_single_lens_stream_is_rejected_with_the_reason():
    """Not 2:1 means single-lens mode -- say so, do not upload."""
    with pytest.raises(NotPanoramic, match="360 view"):
        SSHCamera("fake@host", command=producer(640, 480))


def test_a_silent_host_fails_with_something_actionable():
    quiet = [sys.executable, "-c", "import time; time.sleep(30)"]
    with pytest.raises(RemoteCameraError, match="ffmpeg or gst-launch"):
        SSHCamera("fake@host", command=quiet, connect_timeout=1.0)


def test_junk_before_the_first_marker_is_skipped():
    """A remote shell may print a banner before the video starts."""
    noisy = "import sys\nsys.stdout.buffer.write(b'Welcome to Ubuntu 20.04\\n')\n" + PRODUCER
    with SSHCamera("fake@host", command=producer(script=noisy)) as cam:
        assert cam.resolution == (640, 320)


def test_closing_twice_is_harmless():
    cam = SSHCamera("fake@host", command=producer())
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
