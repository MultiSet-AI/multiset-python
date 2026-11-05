"""Discovery must stay quiet, and must not guess.

A machine with no camera is normal -- someone who has not plugged it in yet.
Probing absent devices makes OpenCV print a paragraph each, burying the one
line that says what to do.
"""

from __future__ import annotations

import os
import sys

import pytest
from multiset.insta360 import CameraNotFound, UsbCamera
from multiset.insta360.camera import _opencv_quiet


def test_the_silencer_restores_stderr():
    """It redirects fd 2; a leak would silence the whole program."""
    before = os.dup(2)
    try:
        with _opencv_quiet():
            pass
        after = os.dup(2)
        os.close(after)
    finally:
        os.close(before)
    print("stderr still works", file=sys.stderr)


def test_the_silencer_restores_stderr_on_an_exception():
    with pytest.raises(RuntimeError), _opencv_quiet():
        raise RuntimeError("boom")
    print("stderr still works after a raise", file=sys.stderr)


def test_an_empty_video4linux_means_no_camera_without_probing(monkeypatch, tmp_path):
    """An empty sysfs directory is a definite answer -- take it.

    Falling through to index probing is what produced the warning wall, and
    could never have succeeded.
    """
    empty = tmp_path / "video4linux"
    empty.mkdir()
    real_path = __import__("multiset.insta360.camera", fromlist=["Path"]).Path

    class FakePath(type(real_path())):  # type: ignore[misc]
        def __new__(cls, *args, **kwargs):
            if args and args[0] == "/sys/class/video4linux":
                return real_path(empty)
            return real_path(*args, **kwargs)

    monkeypatch.setattr("multiset.insta360.camera.Path", FakePath)

    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not probe when sysfs already says there is none")

    monkeypatch.setattr("multiset.insta360.camera.cv2.VideoCapture", explode)
    assert UsbCamera._discover() is None


def test_the_error_says_how_to_fix_it():
    error = CameraNotFound()
    assert "Webcam mode" in str(error)
