"""A camera and a client, in a loop that keeps answering "where am I?".

    for pose in Localizer(cam).stream(interval=2.0):
        if pose:
            print(pose.x, pose.y, pose.yaw_deg)

What this adds over calling `localize()` yourself is hint chaining: each fix
narrows the next search. A lost pose drops the hint, since a stale one pins the
search where the camera no longer is.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

from multiset.vps import PanoramaSource, Pose, VPSClient, VPSSettings, pose_to_hint

log = logging.getLogger(__name__)

#: Tighter than the service's default of 25 m: two seconds is not far.
DEFAULT_HINT_RADIUS = 15.0


class Localizer:
    """Repeated localization from one 360 camera, with the hints chained."""

    def __init__(
        self,
        camera: PanoramaSource,
        client: VPSClient | None = None,
        settings: VPSSettings | None = None,
        *,
        map_code: str | None = None,
        use_hints: bool = True,
        hint_radius: float = DEFAULT_HINT_RADIUS,
        attempts: int = 8,
    ) -> None:
        """One `client` is reused for every query: it holds the cached token.

        `attempts` retries a 5xx, which is how a waking query GPU reports
        itself -- the first fix after a pause can take minutes.
        """
        self.camera = camera
        self.client = client or VPSClient(settings)
        self.map_code = map_code
        self.use_hints = use_hints
        self.hint_radius = hint_radius
        self.attempts = attempts
        self.hint: tuple[float, float, float] | None = None

    def localize_once(self) -> Pose:
        """Grab a frame and localize it, feeding in the previous fix as a hint."""
        (panorama,) = self.camera.capture_panorama()
        query: dict[str, object] = {"attempts": self.attempts}
        if self.map_code:
            query["map_code"] = self.map_code
        if self.use_hints and self.hint is not None:
            query["hint_position"] = self.hint
            query["hint_radius"] = self.hint_radius

        pose = self.client.localize_panorama(panorama, **query)  # type: ignore[arg-type]
        # a stale hint holds the search where the camera no longer is
        self.hint = pose_to_hint(pose) if pose else None
        return pose

    def stream(self, interval: float = 2.0) -> Iterator[Pose]:
        """Localize repeatedly. `interval` is a floor, not a rate: each query
        blocks, so the real period is whichever is longer."""
        while True:
            started = time.monotonic()
            yield self.localize_once()
            remaining = interval - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)


__all__ = ["DEFAULT_HINT_RADIUS", "Localizer"]
