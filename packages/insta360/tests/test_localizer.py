"""Localizer: the hint chain, and what happens when the pose is lost."""

from __future__ import annotations

import numpy as np
from multiset.insta360 import Localizer
from multiset.vps import Panorama, Pose

FOUND = {
    "poseFound": True,
    "position": {"x": 4.0, "y": 1.0, "z": 2.0},
    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
    "confidence": 0.8,
}
LOST = {"poseFound": False}


class FakeCamera:
    def capture_panorama(self) -> Panorama:
        return Panorama(np.zeros((320, 640, 3), np.uint8))


class RecordingClient:
    """Stands in for VPSClient: scripted answers, recorded calls."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.queries: list[dict] = []

    def localize_panorama(self, image, **query):  # noqa: ARG002 (stub)
        self.queries.append(query)
        return Pose.from_response(self.answers.pop(0))


def test_the_first_query_carries_no_hint():
    client = RecordingClient([FOUND])
    Localizer(FakeCamera(), client).localize_once()
    assert "hint_position" not in client.queries[0]


def test_each_fix_becomes_the_next_query_s_hint_with_x_flipped():
    client = RecordingClient([FOUND, FOUND])
    loc = Localizer(FakeCamera(), client)
    loc.localize_once()
    loc.localize_once()
    assert client.queries[1]["hint_position"] == (-4.0, 1.0, 2.0)
    assert client.queries[1]["hint_radius"] == 15.0


def test_losing_the_pose_drops_the_hint():
    """A stale hint pins the search where the camera no longer is."""
    client = RecordingClient([FOUND, LOST, FOUND])
    loc = Localizer(FakeCamera(), client)
    loc.localize_once()
    loc.localize_once()  # lost -> hint cleared
    loc.localize_once()
    assert "hint_position" in client.queries[1], "the lost query still had the old hint"
    assert "hint_position" not in client.queries[2], "recovery must search wide"
    assert loc.hint is None or loc.hint == (-4.0, 1.0, 2.0)


def test_hints_can_be_turned_off():
    client = RecordingClient([FOUND, FOUND])
    loc = Localizer(FakeCamera(), client, use_hints=False)
    loc.localize_once()
    loc.localize_once()
    assert all("hint_position" not in q for q in client.queries)


def test_cold_start_retries_are_passed_through():
    client = RecordingClient([FOUND])
    Localizer(FakeCamera(), client, attempts=8).localize_once()
    assert client.queries[0]["attempts"] == 8


def test_stream_yields_repeatedly():
    client = RecordingClient([FOUND, LOST, FOUND])
    loc = Localizer(FakeCamera(), client)
    poses = []
    for pose in loc.stream(interval=0):
        poses.append(bool(pose))
        if len(poses) == 3:
            break
    assert poses == [True, False, True]
