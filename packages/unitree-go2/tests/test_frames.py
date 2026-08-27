"""The frame conversions that are silent when wrong."""

from __future__ import annotations

import math

import numpy as np
import pytest
from multiset.unitree.go2 import YUP_TO_ZUP, camera_pose_to_base


def test_yup_to_zup_maps_axes_as_documented():
    """(x, y, z) -> (x, -z, y): the map's up axis becomes Z."""
    point = np.array([1.0, 2.0, 3.0, 1.0])
    assert (YUP_TO_ZUP @ point)[:3] == pytest.approx([1.0, -3.0, 2.0])


def test_yup_to_zup_is_a_rotation():
    R = YUP_TO_ZUP[:3, :3]
    assert np.linalg.det(R) == pytest.approx(1.0)
    assert pytest.approx(np.eye(3)) == (R @ R.T)


def test_camera_pose_to_base_moves_exactly_the_mount_offset():
    """Measured on hardware as 0.300 m -- matching BASE_TO_OPTICAL.

    A VPS pose describes the CAMERA. Drawing it as the robot puts the dog a
    body-length ahead of where it is, and looks entirely plausible.
    """
    T_base = camera_pose_to_base(np.eye(4))
    offset = float(np.linalg.norm(T_base[:3, 3]))
    assert offset == pytest.approx(0.30, abs=1e-6)


def test_camera_and_base_headings_differ():
    """They are ~90 degrees apart, which is why the wrong one is not obvious."""
    identity_yaw = 0.0
    T_base = camera_pose_to_base(np.eye(4))
    base_yaw = math.degrees(math.atan2(T_base[1, 0], T_base[0, 0]))
    assert abs(base_yaw - identity_yaw) > 45


def test_conversion_preserves_rigidity():
    R = camera_pose_to_base(np.eye(4))[:3, :3]
    assert pytest.approx(np.eye(3), abs=1e-9) == (R @ R.T)
    assert np.linalg.det(R) == pytest.approx(1.0)
