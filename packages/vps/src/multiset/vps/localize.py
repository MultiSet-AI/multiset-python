"""One call: a frame source in, a Pose out."""

from __future__ import annotations

import numpy as np

from .client import VPSClient
from .intrinsics import PinholeIntrinsics
from .pose import Pose
from .settings import VPSSettings
from .sources import FrameSource, PanoramaSource


def localize(
    source: FrameSource | PanoramaSource,
    settings: VPSSettings | None = None,
    *,
    client: VPSClient | None = None,
    **query: object,
) -> Pose:
    """Capture one frame from `source` and localize it.

    Takes either camera: `capture_panorama()` goes as an equirect query,
    `capture()` as a pinhole one with its intrinsics.

    Pass `client` in a loop: it holds the cached auth token and the HTTP
    session, so building one per query costs a token request and a TLS
    handshake each time.

    found=False is a normal answer, not an error. Check `if pose:`.
    """
    vps = client or VPSClient(settings)
    # the more specific case first, so a source offering both reads as 360
    if isinstance(source, PanoramaSource):
        (panorama,) = source.capture_panorama()
        return vps.localize_panorama(panorama, **query)  # type: ignore[arg-type]
    image, intrinsics = source.capture()
    return vps.localize(image, intrinsics, **query)  # type: ignore[arg-type]


def localize_image(
    image: np.ndarray,
    intrinsics: PinholeIntrinsics,
    settings: VPSSettings | None = None,
    *,
    client: VPSClient | None = None,
    **query: object,
) -> Pose:
    """Localize an already-rectified image: a file, a dataset, an upload."""
    vps = client or VPSClient(settings)
    return vps.localize(image, intrinsics, **query)  # type: ignore[arg-type]


def localize_panorama(
    image: np.ndarray,
    settings: VPSSettings | None = None,
    *,
    client: VPSClient | None = None,
    **query: object,
) -> Pose:
    """Localize one 2:1 equirectangular image. No intrinsics to supply.

    See `VPSClient.localize_panorama()` for the hint and retry arguments.
    """
    vps = client or VPSClient(settings)
    return vps.localize_panorama(image, **query)  # type: ignore[arg-type]


__all__ = ["localize", "localize_image", "localize_panorama"]
