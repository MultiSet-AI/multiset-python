"""MultiSet VPS: an undistorted frame in, a pose out.

API (docs.multiset.ai):
    POST /m2m/token           Basic b64(id:secret)  -> JWT, 30 min
    POST /vps/map/query-form  Bearer <jwt>, multipart:
         mapCode, fx, fy, px, py, width, height, isRightHanded,
         queryImage (jpeg), optional queryMode / hintPosition / hintRadius /
         hintFloorHeight -- the hints are comma-separated STRINGS, see
         _hint_fields()
    ->   {poseFound, position{x,y,z}, rotation{x,y,z,w}, confidence, mapCodes,
          responseTime}

Note that poseFound=false is NOT an error and does not raise. A featureless
wall legitimately fails to localize, and callers that had to wrap every query in
a try/except would learn to swallow real failures too.

Give it an image and the intrinsics describing that image.
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

import cv2
import numpy as np
import requests

from .errors import VPSAuthError, VPSError
from .intrinsics import PinholeIntrinsics
from .pose import Pose
from .settings import VPSSettings

log = logging.getLogger(__name__)

# The API caps query images at 1280 px on the longest side. Downscaling must
# scale the intrinsics with the image or every bearing is wrong.
MAX_IMAGE_DIM = 1280


class VPSClient:
    """Auth plus a single-image localize call."""

    def __init__(self, settings: VPSSettings | None = None) -> None:
        self.settings = settings or VPSSettings.from_env()
        # Auth only: the map is per-call, so requiring one here would block
        # every endpoint that is not a single-map query.
        self.client_id, self.client_secret = self.settings.require_auth()
        self.api_base = self.settings.api_base
        self._token: str | None = None
        self._token_expires = 0.0
        # Reused across calls, so only the first pays a TLS handshake.
        self._session = requests.Session()

    def close(self) -> None:
        """Release the HTTP session. Safe to call twice."""
        self._session.close()

    def __enter__(self) -> VPSClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- auth --------------------------------------------------------------

    def token(self) -> str:
        """A valid JWT, refreshed within 60 s of the 30-minute expiry.

        Cached on the instance: one localize per second for half an hour is one
        token, not eighteen hundred.
        """
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        try:
            response = self._session.post(
                f"{self.api_base}/m2m/token",
                headers={"Authorization": f"Basic {basic}", "Content-Type": "application/json"},
                json={"clientId": self.client_id, "clientSecret": self.client_secret},
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise VPSAuthError(f"could not reach the MultiSet token endpoint: {exc}") from exc
        data = response.json()
        if data.get("error"):
            raise VPSAuthError(f"MultiSet auth failed: {data['error']}")
        self._token = data["token"]
        self._token_expires = time.time() + 30 * 60
        assert self._token
        return self._token

    # -- one way in and out of the API -------------------------------------

    def _request(
        self, method: str, path: str, *, timeout: float | None = None, **kwargs: Any
    ) -> dict:
        """Every authenticated call goes through here: bearer header, timeout,
        session reuse, and HTTP failure -> VPSError."""
        url = f"{self.api_base}{path}"
        try:
            response = self._session.request(
                method,
                url,
                headers={"Authorization": f"Bearer {self.token()}"},
                timeout=self.settings.timeout if timeout is None else timeout,
                **kwargs,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            # The body carries the reason; without it a 400 is just a number.
            detail = ""
            failed = exc.response
            if failed is not None and failed.text:
                detail = f": {failed.text[:300]}"
            raise VPSError(f"{method} {path} failed: {exc}{detail}") from exc
        try:
            return response.json()
        except ValueError as exc:
            body = response.text[:200]
            raise VPSError(f"{method} {path} returned non-JSON: {body!r}") from exc

    # -- request fields ----------------------------------------------------

    @staticmethod
    def _hint_fields(
        hint_position: tuple[float, float, float] | None = None,
        hint_radius: float | None = None,
        hint_floor_height: tuple[float, float] | None = None,
    ) -> dict[str, tuple[None, str]]:
        """The optional search hints, in the shapes the API actually accepts.

        All three are BARE COMMA-SEPARATED STRINGS -- "x,y,z" and "y_min,y_max"
        -- not JSON arrays and not objects. The published docs write them as
        [x, y, z], which reads like JSON but is notation for "three values":
        sending a real JSON array is rejected with

            Invalid hintPosition format. It should be a string in the
            format "x,y,z".

        Verified against the live API. The previous dict form was rejected the
        same way, and nothing noticed because no caller ever passed a hint.

        Shared by every query endpoint -- single-image and multi-image take the
        same three.
        """
        fields: dict[str, tuple[None, str]] = {}
        if hint_position is not None:
            if len(hint_position) != 3:
                raise ValueError(f"hint_position is (x, y, z); got {hint_position!r}")
            fields["hintPosition"] = (None, ",".join(f"{float(v):.4f}" for v in hint_position))
        if hint_radius is not None:
            # The server 400s above 100 and defaults to 25 when absent.
            if not 5.0 <= float(hint_radius) <= 100.0:
                raise ValueError(f"hint_radius must be between 5 and 100 m; got {hint_radius}")
            fields["hintRadius"] = (None, f"{float(hint_radius):g}")
        if hint_floor_height is not None:
            if len(hint_floor_height) != 2:
                raise ValueError(
                    f"hint_floor_height is a RANGE (y_min, y_max), not a single "
                    f"height; got {hint_floor_height!r}"
                )
            fields["hintFloorHeight"] = (
                None,
                ",".join(f"{float(v):.4f}" for v in hint_floor_height),
            )
        return fields

    # -- localize ----------------------------------------------------------

    def localize(
        self,
        image: np.ndarray,
        intrinsics: PinholeIntrinsics,
        *,
        map_code: str | None = None,
        map_ids: list[str] | None = None,
        query_mode: str | None = None,
        hint_position: tuple[float, float, float] | None = None,
        hint_radius: float | None = None,
        hint_floor_height: tuple[float, float] | None = None,
        is_right_handed: bool = True,
        timeout: float | None = None,
    ) -> Pose:
        """Localize one UNDISTORTED frame.

        `image` is the rectified array and `intrinsics` must describe THAT
        array -- the pair Rectifier.undistort() returns. They travel together
        for a reason: sending a raw fisheye focal length with a rectified image
        is a ~10% error on every bearing, and the server still answers
        poseFound=true. Wrong, confidently.

        isRightHanded selects the HANDEDNESS of the returned pose, not the up
        axis -- the pose comes back Y-up either way. Setting it false negates X
        and permutes the quaternion, flipping the sign of the final heading, so
        anything steering on it turns the wrong way. Keep it True.

        The map comes from `map_code`, or `map_ids`, or MULTISET_MAP_CODE, in
        that order.

        Hints narrow the search when you already have a rough idea where the
        camera is:

            hint_position      (x, y, z) in the map frame
            hint_radius        metres, 5..100; the server defaults to 25
            hint_floor_height  (y_min, y_max) -- a RANGE, not one height

        A hint the server cannot parse is not rejected: it searches the whole
        map and answers as though you had not hinted, so a wrong shape looks
        like a hint that did not help.
        """
        if not isinstance(image, np.ndarray):
            raise TypeError(
                f"localize() takes the undistorted image as a numpy array, got "
                f"{type(image).__name__}. Use a FrameSource's capture(), or "
                f"Rectifier.undistort(frame)."
            )

        height, width = image.shape[:2]
        scale = min(1.0, MAX_IMAGE_DIM / max(width, height))
        if scale < 1.0:
            image = cv2.resize(image, (int(width * scale), int(height * scale)))
            height, width = image.shape[:2]
            intrinsics = intrinsics.scaled(scale, width, height)

        ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            raise VPSError("JPEG encode failed")

        # require_map returns plain data; multipart wrapping belongs here.
        resolved_map = self.settings.require_map(map_code, map_ids)
        map_fields = {key: (None, value) for key, value in resolved_map.items()}

        form: dict[str, Any] = {
            **map_fields,
            "fx": (None, f"{float(intrinsics.fx):.4f}"),
            "fy": (None, f"{float(intrinsics.fy):.4f}"),
            "px": (None, f"{float(intrinsics.px):.4f}"),
            "py": (None, f"{float(intrinsics.py):.4f}"),
            "width": (None, str(width)),
            "height": (None, str(height)),
            "isRightHanded": (None, "true" if is_right_handed else "false"),
            "queryImage": ("query.jpg", buffer.tobytes(), "image/jpeg"),
            **self._hint_fields(hint_position, hint_radius, hint_floor_height),
        }
        mode = query_mode or self.settings.query_mode
        if mode:
            form["queryMode"] = (None, mode)

        data = self._request("POST", "/vps/map/query-form", files=form, timeout=timeout)
        pose = Pose.from_response(data)
        log.debug("vps: %s", pose)
        return pose


__all__ = ["MAX_IMAGE_DIM", "VPSClient"]
