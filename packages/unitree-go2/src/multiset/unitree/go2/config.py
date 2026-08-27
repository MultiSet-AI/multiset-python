"""What it takes to reach one Go2. VPS credentials are NOT in here.

They are two different things with two different owners: the address and AES key
belong to the robot in front of you, the MultiSet client id and map code belong
to your account and are the same for every device you run. Keeping them in one
object made a capture-only script demand credentials it never used.

Both read the same .env, using the same parser -- see multiset.vps.settings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path

from multiset.vps.settings import env_value, find_env_file, parse_env_file

from .errors import ConfigError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Go2Settings:
    """Address, credentials and timeouts for one robot."""

    robot_ip: str | None = None
    aes_key: str | None = field(default=None, repr=False)
    serial: str | None = None
    jetson_ip: str | None = None

    connect_timeout: float = 30.0
    frame_timeout: float = 20.0
    settle: float = 0.4

    @classmethod
    def from_env(cls, env_file: str | Path | None = None, **overrides: object) -> Go2Settings:
        """Read a .env file and the process environment, then apply overrides.

        Precedence, lowest to highest: .env file, real environment variables,
        explicit keyword arguments. Real environment beats the file so that
        `GO2_IP=... python app.py` works without editing anything.
        """
        path = Path(env_file) if env_file else find_env_file()
        values = parse_env_file(path) if path else {}
        if path:
            log.debug("settings: read %s", path)
        settings = cls(
            robot_ip=env_value("GO2_IP", values),
            aes_key=env_value("GO2_AES_KEY", values),
            serial=env_value("GO2_SN", values),
            jetson_ip=env_value("GO2_JETSON_IP", values),
        )
        return replace(settings, **overrides) if overrides else settings  # type: ignore[arg-type]

    def require_robot(self) -> str:
        """The robot's address, or a ConfigError explaining how to get one."""
        if not self.robot_ip:
            raise ConfigError(
                "no robot address. Set GO2_IP in .env or pass "
                "Go2Settings(robot_ip=...).\n"
                "It is the GO2 HEAD UNIT's address -- the computer with only port "
                "9991 open. A Go2 with a Jetson board puts two hosts on your wifi, "
                "and the other one never serves WebRTC."
            )
        return self.robot_ip

    def redacted(self) -> dict[str, object]:
        """A dict safe to log: secrets become lengths, not values."""

        def mask(value: str | None) -> str:
            return f"<set, {len(value)} chars>" if value else "<unset>"

        return {
            "robot_ip": self.robot_ip,
            "serial": self.serial,
            "jetson_ip": self.jetson_ip,
            "aes_key": mask(self.aes_key),
        }


__all__ = ["Go2Settings"]
