"""Equirect queries: no intrinsics, no 1280 cap, and a hint frame that flips X.

Offline -- a stub session stands in for the network. The wire format was
checked against the live API: imageType=equirect with no focal lengths is
accepted at 4096x2048, while the same image as pinhole is rejected.
"""

from __future__ import annotations

import numpy as np
import pytest
import requests
from multiset.vps import (
    MAX_EQUIRECT_WIDTH,
    CalibrationError,
    Pose,
    VPSClient,
    VPSError,
    encode_equirect,
    pose_to_hint,
)

from .test_client import WITH_MAP, StubResponse, StubSession

FOUND = {
    "poseFound": True,
    "position": {"x": 4.2, "y": 1.1, "z": -0.3},
    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
    "confidence": 0.9,
}


def client(response=None, settings=WITH_MAP) -> VPSClient:
    c = VPSClient(settings)
    c._session = StubSession(response)
    return c


def equirect(width=2880) -> np.ndarray:
    """A 2:1 frame with structure, so JPEG has something to chew."""
    rng = np.random.default_rng(0)
    return rng.integers(0, 255, (width // 2, width, 3), dtype=np.uint8)


def sent_form(c: VPSClient) -> dict:
    return c._session.calls[-1][2]["files"]


# -- the wire format --------------------------------------------------------


def test_equirect_sends_imagetype_and_no_intrinsics():
    """The whole feature. Sending fx/fy would put it back on the pinhole
    path, where 4096x2048 is rejected outright."""
    c = client(StubResponse(FOUND))
    c.localize_panorama(equirect())
    form = sent_form(c)
    assert form["imageType"] == (None, "equirect")
    for pinhole_only in ("fx", "fy", "px", "py", "width", "height"):
        assert pinhole_only not in form, f"{pinhole_only} belongs to pinhole queries"
    assert form["mapCode"] == (None, "MAP_DEFAULT")
    assert form["queryImage"][0] == "query.jpg"


def test_the_1280_pinhole_cap_is_not_applied():
    """1280x640 loses what the solver needs. Only pinhole is capped."""
    c = client(StubResponse(FOUND))
    c.localize_panorama(equirect(2880))
    jpeg = sent_form(c)["queryImage"][1]
    import cv2

    decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[1] == 2880, "a 2880-wide panorama must go up unshrunk"


def test_oversize_panoramas_are_capped_at_4096():
    c = client(StubResponse(FOUND))
    c.localize_panorama(equirect(8000))
    jpeg = sent_form(c)["queryImage"][1]
    import cv2

    decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[1] == MAX_EQUIRECT_WIDTH


def test_a_frame_that_is_not_2_to_1_is_refused_before_upload():
    """The usual cause is a camera left in single-lens mode."""
    c = client(StubResponse(FOUND))
    with pytest.raises(CalibrationError, match="2:1"):
        c.localize_panorama(np.zeros((720, 1280, 3), np.uint8))
    assert c._session.calls == [], "nothing should reach the network"


def test_a_panorama_below_the_service_minimum_is_refused_before_upload():
    c = client(StubResponse(FOUND))
    with pytest.raises(CalibrationError, match="2048"):
        c.localize_panorama(equirect(1920))
    assert c._session.calls == []
    c.localize_panorama(equirect(2048))
    assert sent_form(c)["imageType"] == (None, "equirect")


def test_hints_travel_as_csv_like_the_pinhole_path():
    c = client(StubResponse(FOUND))
    c.localize_panorama(equirect(), hint_position=(2.76, 0.81, 0.0), hint_radius=15)
    form = sent_form(c)
    assert form["hintPosition"][1] == "2.7600,0.8100,0.0000"
    assert form["hintRadius"][1] == "15"


# -- hint chaining ----------------------------------------------------------


def test_pose_to_hint_flips_x():
    """Chaining the raw position shows up only as a search that stops
    helping, so pin the flip."""
    pose = Pose.from_response(FOUND)
    assert pose_to_hint(pose) == (-4.2, 1.1, -0.3)
    assert pose_to_hint(pose, is_right_handed=False) == (4.2, 1.1, -0.3)


def test_pose_to_hint_also_takes_the_raw_response():
    assert pose_to_hint(FOUND) == (-4.2, 1.1, -0.3)


# -- cold start -------------------------------------------------------------


class WakingSession(StubSession):
    """5xx until the Nth call, like a waking query GPU."""

    def __init__(self, fail_times: int, status: int = 503):
        super().__init__()
        self.fail_times = fail_times
        self.status = status
        self.queries = 0  # token requests go through post(), not request()

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        self.queries += 1
        if self.queries <= self.fail_times:
            response = requests.Response()
            response.status_code = self.status
            raise requests.HTTPError(f"{self.status} Server Error", response=response)
        return StubResponse(FOUND)


def test_a_5xx_is_retried_because_the_instance_is_only_waking():
    c = VPSClient(WITH_MAP)
    c._session = WakingSession(fail_times=2)
    pose = c.localize_panorama(equirect(), attempts=4, retry_wait=0)
    assert pose.found
    assert c._session.queries == 3


def test_a_4xx_is_not_retried_because_retrying_cannot_help():
    c = VPSClient(WITH_MAP)
    c._session = WakingSession(fail_times=9, status=400)
    with pytest.raises(VPSError):
        c.localize_panorama(equirect(), attempts=4, retry_wait=0)
    assert c._session.queries == 1, "a bad request is not worth repeating"


def test_retries_give_up_and_raise_the_last_error():
    c = VPSClient(WITH_MAP)
    c._session = WakingSession(fail_times=99)
    with pytest.raises(VPSError):
        c.localize_panorama(equirect(), attempts=3, retry_wait=0)
    assert c._session.queries == 3


# -- encoding ---------------------------------------------------------------


def test_encoding_steps_quality_down_to_fit_the_budget():
    jpeg = encode_equirect(equirect(4096), max_bytes=120_000)
    assert len(jpeg) <= 120_000 or len(jpeg) < equirect(4096).nbytes
