"""Every failure this package raises.

Insta360Error subclasses MultisetError, so one `except MultisetError` covers
this package, the core, and every other device beside it.
"""

from __future__ import annotations

from multiset.vps import CameraError, MultisetError


class Insta360Error(MultisetError):
    """Base for every error raised by multiset.insta360."""


class CameraNotFound(Insta360Error):
    """No Insta360 camera was found on this machine."""

    def __init__(self) -> None:
        super().__init__(
            "no Insta360 camera found. Plug it in over USB, then pick "
            "Webcam mode -> 360 view on the camera's own screen."
        )


class NotPanoramic(Insta360Error):
    """The device is delivering frames, but not a 2:1 panorama."""

    def __init__(self, source: str, width: int, height: int) -> None:
        super().__init__(
            f"{source} delivers {width}x{height}, which is not the 2:1 shape of "
            f"an equirectangular frame. The camera is almost certainly in single-lens "
            f"mode -- choose 360 view in the webcam prompt on its screen."
        )


__all__ = [
    "CameraError",
    "CameraNotFound",
    "Insta360Error",
    "NotPanoramic",
]
