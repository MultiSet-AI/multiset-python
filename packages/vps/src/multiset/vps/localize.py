"""One call: a frame source in, a Pose out."""

from __future__ import annotations

import numpy as np

from .client import VPSClient
from .intrinsics import PinholeIntrinsics
from .pose import Pose
from .settings import VPSSettings
from .sources import FrameSource


def localize(
    source: FrameSource,
    settings: VPSSettings | None = None,
    *,
    client: VPSClient | None = None,
    **query: object,
) -> Pose:
    """Capture one frame from `source` and localize it.

    Pass `client` in a loop: it holds the cached auth token and the HTTP
    session, so building one per query costs a token request and a TLS
    handshake each time.

    found=False is a normal answer, not an error. Check `if pose:`.
    """
    image, intrinsics = source.capture()
    vps = client or VPSClient(settings)
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


__all__ = ["localize", "localize_image"]
