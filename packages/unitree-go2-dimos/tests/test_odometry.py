"""Composing odometry onto a VPS fix.

The maths that puts the robot in the right room. It is ported from the
navigator deliberately unchanged, so these tests pin the behaviour rather than
merely exercising it.
"""

from __future__ import annotations

import math

import pytest
from multiset.unitree.go2.dimos import compose_map_from_odom


def test_at_the_anchor_the_fix_is_reproduced_exactly():
    anchor_map = (2.76, 1.43, math.radians(-40))
    anchor_odom = (0.5, -0.2, math.radians(15))
    x, y, yaw = compose_map_from_odom(anchor_map, anchor_odom, anchor_odom)
    assert (x, y) == pytest.approx(anchor_map[:2])
    assert yaw == pytest.approx(anchor_map[2])


def test_forward_in_odom_is_forward_in_the_map():
    """A metre of odometry travel is a metre in the map, rotated into its frame."""
    anchor_map = (0.0, 0.0, math.radians(90))  # robot faces map +Y
    anchor_odom = (0.0, 0.0, 0.0)  # odom frame faces its own +X
    x, y, _ = compose_map_from_odom(anchor_map, anchor_odom, (1.0, 0.0, 0.0))
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(1.0)


def test_rotation_carries_through():
    anchor_map = (0.0, 0.0, 0.0)
    anchor_odom = (0.0, 0.0, 0.0)
    _, _, yaw = compose_map_from_odom(anchor_map, anchor_odom, (0.0, 0.0, math.radians(30)))
    assert math.degrees(yaw) == pytest.approx(30.0)


def test_yaw_wraps_rather_than_accumulating():
    """Heading must stay in (-pi, pi] or comparisons downstream go wrong."""
    anchor_map = (0.0, 0.0, math.radians(170))
    anchor_odom = (0.0, 0.0, 0.0)
    _, _, yaw = compose_map_from_odom(anchor_map, anchor_odom, (0.0, 0.0, math.radians(30)))
    assert -math.pi < yaw <= math.pi
    assert math.degrees(yaw) == pytest.approx(-160.0)


def test_translation_is_expressed_in_the_anchor_frame():
    """Sideways odometry with a rotated anchor must not leak into the wrong axis."""
    anchor_map = (5.0, 5.0, math.radians(180))
    anchor_odom = (0.0, 0.0, 0.0)
    x, y, _ = compose_map_from_odom(anchor_map, anchor_odom, (2.0, 0.0, 0.0))
    assert x == pytest.approx(3.0)
    assert y == pytest.approx(5.0, abs=1e-9)
