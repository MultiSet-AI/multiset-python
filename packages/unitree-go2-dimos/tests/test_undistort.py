from __future__ import annotations

import numpy as np
import pytest
from multiset.unitree.go2.dimos import FRONT, GO2_FRONT_720P
from multiset.vps import CalibrationError, Rectifier


def test_rectified_intrinsics_are_the_known_values():
    """Pinned against the reference implementation this was ported from.

    These four numbers are what VPS is told about every frame; a silent change
    here is a silent bearing error on every pose.
    """
    K = FRONT.intrinsics
    assert K.fx == pytest.approx(728.474824, abs=1e-5)
    assert K.fy == pytest.approx(727.571939, abs=1e-5)
    assert K.px == pytest.approx(646.640703, abs=1e-5)
    assert K.py == pytest.approx(346.461648, abs=1e-5)


def test_rectified_focal_is_shorter_than_raw():
    """balance=0.0 crops to valid pixels, which shortens the focal length.

    This is the distinction the whole module exists to protect: raw ~797
    describes the sensor, rectified ~728 describes the undistorted image, and
    swapping them is a ~10% error that VPS answers poseFound=true to.
    """
    assert FRONT.intrinsics.fx < GO2_FRONT_720P.fx
    assert GO2_FRONT_720P.fx / FRONT.intrinsics.fx == pytest.approx(1.09, abs=0.02)


def test_undistort_returns_image_and_matching_intrinsics(frame_720p):
    image, K = FRONT.undistort(frame_720p)
    assert image.shape == frame_720p.shape
    assert (K.width, K.height) == (1280, 720)
    assert K.source == "go2-front-720p"
    assert not np.array_equal(image, frame_720p)  # it actually remapped


def test_wrong_size_is_refused_not_silently_wrong():
    """A resized frame must raise, not produce plausible-but-wrong geometry."""
    with pytest.raises(CalibrationError, match="1280x720"):
        FRONT.undistort(np.zeros((480, 640, 3), np.uint8))


def test_fov_is_plausible_for_this_lens():
    K = FRONT.intrinsics
    assert 80 < K.hfov_deg < 85
    assert 50 < K.vfov_deg < 56


def test_maps_are_cached():
    """Rebuilding the remap tables per frame would cost milliseconds at 14 fps."""
    from multiset.vps.intrinsics import _rectify_maps

    _rectify_maps.cache_clear()
    first = Rectifier(GO2_FRONT_720P).intrinsics
    second = Rectifier(GO2_FRONT_720P).intrinsics
    assert first == second
    assert _rectify_maps.cache_info().hits >= 1


def test_intrinsics_scale_with_a_resized_image():
    """The client downsizes oversized queries; the intrinsics must follow."""
    K = FRONT.intrinsics
    half = K.scaled(0.5, K.width // 2, K.height // 2)
    assert half.fx == pytest.approx(K.fx / 2)
    assert half.px == pytest.approx(K.px / 2)
    assert half.hfov_deg == pytest.approx(K.hfov_deg, abs=0.01)  # same view
