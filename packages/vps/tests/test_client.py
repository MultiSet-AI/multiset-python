"""The client: request fields in, response types out.

All offline. A stub session stands in for the network, so these run with no
credentials and no MultiSet account.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
import requests
from multiset.vps import ConfigError, Pose, VPSAuthError, VPSClient, VPSError, VPSSettings

AUTH = VPSSettings(client_id="id", client_secret="secret")
WITH_MAP = VPSSettings(client_id="id", client_secret="secret", map_code="MAP_DEFAULT")


class StubResponse:
    def __init__(self, payload=None, *, text="", raises=None):
        self._payload = payload
        self.text = text
        self._raises = raises

    def raise_for_status(self):
        if self._raises:
            raise self._raises

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class StubSession:
    """Records what the client sent and replays canned answers."""

    def __init__(self, response=None):
        self.response = response or StubResponse({})
        self.calls = []

    def post(self, url, **kwargs):  # the token endpoint
        self.calls.append(("POST", url, kwargs))
        return StubResponse({"token": "jwt-abc"})

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response

    def close(self):
        pass


def client(settings=AUTH, response=None) -> VPSClient:
    c = VPSClient(settings)
    c._session = StubSession(response)
    return c


# -- construction -----------------------------------------------------------


def test_client_builds_without_a_map_code():
    """A map is a property of the CALL, not of the client.

    Listing maps, checking status and uploading need auth and no map code.
    """
    assert VPSClient(AUTH).client_id == "id"


def test_client_still_requires_auth():
    with pytest.raises(ConfigError, match="MULTISET_CLIENT_SECRET"):
        VPSClient(VPSSettings(client_id="id"))


class RejectingSession(StubSession):
    def __init__(self, failure):
        super().__init__()
        self.failure = failure

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if isinstance(self.failure, requests.Response):
            return StubResponse(raises=requests.HTTPError(response=self.failure))
        raise self.failure


def _http(status: int, body: dict) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body).encode()
    return response


def test_rejected_credentials_name_the_credentials_not_the_network():
    """The service answers a wrong secret with 404, which reads like a bad URL."""
    c = VPSClient(AUTH)
    c._session = RejectingSession(_http(404, {"message": "Invalid client id or client secret"}))
    with pytest.raises(VPSAuthError, match="MULTISET_CLIENT_SECRET") as caught:
        c.token()
    assert "Invalid client id or client secret" in str(caught.value)
    assert "could not reach" not in str(caught.value)
    assert caught.value.status == 404


def test_an_unreachable_token_endpoint_still_says_so():
    c = VPSClient(AUTH)
    c._session = RejectingSession(requests.ConnectionError("connection refused"))
    with pytest.raises(VPSAuthError, match="could not reach"):
        c.token()


# -- hint fields -----------------------------------------------------------


def test_hint_position_is_a_csv_string():
    """Verified against the live API: "x,y,z", not JSON and not an object.

    The docs write [x, y, z], which reads like a JSON array. It is not: a JSON
    array is rejected with `Invalid hintPosition format. It should be a string
    in the format "x,y,z".`
    """
    fields = VPSClient._hint_fields(hint_position=(1.0, 2.0, 3.0))
    assert fields["hintPosition"][1] == "1.0000,2.0000,3.0000"
    assert not fields["hintPosition"][1].startswith("[")


def test_hint_floor_height_is_a_csv_range():
    """ "y_min,y_max" -- a range, and a string. A scalar 400s."""
    fields = VPSClient._hint_fields(hint_floor_height=(0.0, 2.5))
    assert fields["hintFloorHeight"][1] == "0.0000,2.5000"


def test_hint_floor_height_rejects_a_single_number():
    with pytest.raises(ValueError, match="RANGE"):
        VPSClient._hint_fields(hint_floor_height=(1.5,))  # type: ignore[arg-type]


def test_hint_position_rejects_the_wrong_length():
    with pytest.raises(ValueError, match=r"\(x, y, z\)"):
        VPSClient._hint_fields(hint_position=(1.0, 2.0))  # type: ignore[arg-type]


def test_hint_radius_is_supported_and_range_checked():
    """5..100. The server rejects anything above 100, and defaults to 25 if absent."""
    assert VPSClient._hint_fields(hint_radius=5.0)["hintRadius"][1] == "5"
    for bad in (4.9, 101.0):
        with pytest.raises(ValueError, match="between 5 and 100"):
            VPSClient._hint_fields(hint_radius=bad)


def test_no_hints_means_no_hint_fields():
    assert VPSClient._hint_fields() == {}


# -- map identity -----------------------------------------------------------


def test_map_code_can_come_from_the_call_alone():
    """Resolves with no MULTISET_MAP_CODE configured."""
    assert AUTH.require_map(map_code="MAP_X") == {"mapCode": "MAP_X"}


def test_map_ids_are_accepted_as_an_alternative():
    assert json.loads(AUTH.require_map(map_ids=["a", "b"])["mapIds"]) == ["a", "b"]


def test_the_call_beats_the_setting():
    assert WITH_MAP.require_map(map_code="MAP_OVERRIDE") == {"mapCode": "MAP_OVERRIDE"}


def test_no_map_anywhere_is_an_error():
    with pytest.raises(ConfigError, match="no map to query"):
        AUTH.require_map()


# -- responses --------------------------------------------------------------


PAYLOAD = {
    "poseFound": True,
    "position": {"x": 2.464, "y": 0.402, "z": -0.796},
    "rotation": {"x": 0.0, "y": 0.7071, "z": 0.0, "w": 0.7071},
    "confidence": 0.569,
    "responseTime": 872,
    "mapCodes": ["MAP_X98UFJB9RWTV"],
    "mapIds": ["69c420204c385bd418cadfff"],
}


def test_pose_from_response_reads_every_field():
    pose = Pose.from_response(PAYLOAD)
    assert pose.found
    assert (pose.x, pose.y, pose.z) == pytest.approx((2.464, 0.402, -0.796))
    assert pose.confidence == pytest.approx(0.569)
    assert pose.response_ms == pytest.approx(872)
    assert pose.map_codes == ("MAP_X98UFJB9RWTV",)


def test_pose_keeps_map_ids():
    """The reply carries mapIds as well as mapCodes."""
    assert Pose.from_response(PAYLOAD).map_ids == ("69c420204c385bd418cadfff",)


def test_pose_not_found_is_a_result_not_an_error():
    pose = Pose.from_response({"poseFound": False, "responseTime": 711})
    assert not pose
    assert not pose.found
    assert pose.response_ms == pytest.approx(711)


def test_pose_from_a_nested_envelope():
    """multi-image-query nests the pose under estimatedPose."""
    nested = {"poseFound": True, "estimatedPose": PAYLOAD, "confidence": 0.4}
    pose = Pose.from_response(nested, position_key="estimatedPose")
    assert (pose.x, pose.y) == pytest.approx((2.464, 0.402))


# -- the request seam -------------------------------------------------------


def test_request_maps_http_failure_to_vps_error():
    boom = requests.ConnectTimeout("connection timed out")
    c = client(response=StubResponse(raises=boom))
    with pytest.raises(VPSError, match="POST /vps/map/query-form failed"):
        c._request("POST", "/vps/map/query-form")


def test_request_maps_non_json_to_vps_error():
    c = client(response=StubResponse(None, text="<html>502 Bad Gateway</html>"))
    with pytest.raises(VPSError, match="non-JSON"):
        c._request("POST", "/vps/maps")


def test_request_sends_the_bearer_token():
    c = client(response=StubResponse({"ok": True}))
    c._request("GET", "/vps/maps")
    method, url, kwargs = c._session.calls[-1]
    assert (method, url) == ("GET", "https://api.multiset.ai/v1/vps/maps")
    assert kwargs["headers"]["Authorization"] == "Bearer jwt-abc"


def test_localize_puts_the_hints_on_the_wire():
    """End to end through the form builder, without a network."""
    c = client(WITH_MAP, StubResponse(PAYLOAD))
    image = np.zeros((720, 1280, 3), np.uint8)

    from multiset.vps import PinholeIntrinsics

    K = PinholeIntrinsics(fx=728.47, fy=727.57, px=646.64, py=346.46, width=1280, height=720)
    pose = c.localize(image, K, hint_position=(2.76, 0.81, 0.0), hint_radius=5.0)

    _, url, kwargs = c._session.calls[-1]
    form = kwargs["files"]
    assert url.endswith("/vps/map/query-form")
    assert form["mapCode"] == (None, "MAP_DEFAULT")
    assert form["hintPosition"][1] == "2.7600,0.8100,0.0000"
    assert form["hintRadius"][1] == "5"
    assert pose.found
