"""Where the camera is. MultiSet credentials are NOT in here.

Same split as every other device package: this says which camera and where,
while the client id, secret and map code belong to your account and live in
`multiset.vps.VPSSettings`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path

from multiset.vps.settings import env_value, find_env_file, parse_env_file

from .errors import Insta360Error

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Insta360Settings:
    """Which camera to open, and whether it is here or on another machine."""

    #: 'user@host' when the camera is on a robot; None means local USB.
    ssh_host: str | None = None
    #: The video device on the far side. Only used with ssh_host.
    device: str = "/dev/video0"
    width: int = 2880
    height: int = 1440
    fps: int = 5
    connect_timeout: float = 25.0

    @classmethod
    def from_env(
        cls, env_file: str | Path | None = None, **overrides: object
    ) -> Insta360Settings:
        """Precedence, lowest to highest: .env file, environment, keyword
        arguments -- so `INSTA360_SSH_HOST=... python app.py` just works."""
        path = Path(env_file) if env_file else find_env_file()
        values = parse_env_file(path) if path else {}
        if path:
            log.debug("settings: read %s", path)
        settings = cls(
            ssh_host=env_value("INSTA360_SSH_HOST", values),
            device=env_value("INSTA360_DEVICE", values) or "/dev/video0",
        )
        return replace(settings, **overrides) if overrides else settings  # type: ignore[arg-type]

    def require_ssh_host(self) -> str:
        """The remote host, or an error explaining how to set one."""
        if not self.ssh_host:
            raise Insta360Error(
                "no remote camera configured. Set INSTA360_SSH_HOST in .env "
                "(e.g. unitree@192.168.123.18) or pass "
                "SSHCamera(host=...).\n"
                "If the camera is plugged into THIS machine, use UsbCamera() "
                "instead -- it takes no host."
            )
        return self.ssh_host


__all__ = ["Insta360Settings"]
