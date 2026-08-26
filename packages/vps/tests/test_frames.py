from __future__ import annotations

import numpy as np
import pytest
from multiset.vps import HANDHELD, YUP_TO_ZUP, Mount, camera_pose_to_origin


def test_yup_to_zup_is_a_rotation():
    R = YUP_TO_ZUP[:3, :3]
    assert np.allclose(R @ R.T, np.eye(3))
    assert np.isclose(np.linalg.det(R), 1.0)


def test_yup_to_zup_lifts_the_up_axis():
    """A point one metre 'up' in VPS (+Y) is one metre up in the map (+Z)."""
    mapped = YUP_TO_ZUP @ np.array([0.0, 1.0, 0.0, 1.0])
    assert np.allclose(mapped[:3], [0.0, 0.0, 1.0])


def test_handheld_mount_is_identity():
    assert np.allclose(HANDHELD.matrix, np.eye(4))


def test_a_mount_moves_the_origin_off_the_lens():
    """A camera 0.3 m ahead of the origin puts the origin 0.3 m behind it."""
    forward = Mount(name="t", translation=(0.3, 0.0, 0.0))
    at_origin = camera_pose_to_origin(np.eye(4), forward)
    handheld = camera_pose_to_origin(np.eye(4), HANDHELD)
    assert np.linalg.norm(at_origin[:3, 3] - handheld[:3, 3]) == pytest.approx(0.3)


def test_quaternion_round_trips_through_a_mount():
    m = Mount(name="q", rotation=(0.0, 0.0, 0.7071067811865476, 0.7071067811865476))
    R = m.matrix[:3, :3]
    assert np.allclose(R @ R.T, np.eye(3))
    assert np.isclose(np.linalg.det(R), 1.0)
