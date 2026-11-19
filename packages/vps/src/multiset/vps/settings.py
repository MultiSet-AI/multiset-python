"""Configuration as a value. Nothing is read at import time."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigError

log = logging.getLogger(__name__)

REGION_API_BASES = {
    "us": "https://api.multiset.ai/v1",
    "eu": "https://api.eu.multiset.ai/v1",
}
DEFAULT_API_BASE = REGION_API_BASES["us"]


def region_for_client_id(client_id: str | None) -> str:
    """The data region a credential belongs to: its prefix (eu_...), else us."""
    prefix, sep, _ = (client_id or "").partition("_")
    return prefix if sep and prefix in REGION_API_BASES else "us"


def api_base_for_client_id(client_id: str | None) -> str:
    return REGION_API_BASES[region_for_client_id(client_id)]


def parse_env_file(path: str | Path) -> dict[str, str]:
    """KEY=VALUE lines -> dict. Blank lines and # comments ignored."""
    p = Path(path)
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def find_env_file(start: str | Path | None = None) -> Path | None:
    """Nearest .env, searching upward from `start` (default: cwd).

    MULTISET_ENV overrides the search entirely.
    """
    if os.environ.get("MULTISET_ENV"):
        candidate = Path(os.environ["MULTISET_ENV"])
        return candidate if candidate.exists() else None
    here = Path(start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def env_value(key: str, values: dict[str, str]) -> str | None:
    """One setting, real environment beating the .env file."""
    return os.environ.get(key) or values.get(key) or None


@dataclass(frozen=True)
class VPSSettings:
    """Credentials and endpoint for MultiSet VPS.

    These belong to your MultiSet account and are reused across every frame
    source; a device's own address and keys belong with that device.
    """

    client_id: str | None = field(default=None, repr=False)
    client_secret: str | None = field(default=None, repr=False)
    map_code: str | None = None
    query_mode: str | None = None
    api_base: str | None = None
    timeout: float = 90.0

    def __post_init__(self) -> None:
        if not self.api_base:
            object.__setattr__(self, "api_base", api_base_for_client_id(self.client_id))

    @classmethod
    def from_env(cls, env_file: str | Path | None = None, **overrides: object) -> VPSSettings:
        """Read a .env file and the environment, then apply overrides.

        Precedence, lowest to highest: .env file, environment, keyword
        arguments. Without MULTISET_API_BASE the endpoint follows the
        client id's region (eu_... -> api.eu.multiset.ai).
        """
        path = Path(env_file) if env_file else find_env_file()
        values = parse_env_file(path) if path else {}
        if path:
            log.debug("settings: read %s", path)
        fields: dict[str, object] = {
            "client_id": env_value("MULTISET_CLIENT_ID", values),
            "client_secret": env_value("MULTISET_CLIENT_SECRET", values),
            "map_code": env_value("MULTISET_MAP_CODE", values),
            "query_mode": env_value("MULTISET_QUERY_MODE", values),
            "api_base": env_value("MULTISET_API_BASE", values),
        }
        fields.update(overrides)
        return cls(**fields)  # type: ignore[arg-type]

    def require_auth(self) -> tuple[str, str]:
        """(client_id, client_secret), or a ConfigError naming what is missing.

        Auth is all a client needs to exist. The API identifies the map per
        request, so requiring one at construction would block every endpoint
        that is not a single-map query.
        """
        missing = [
            name
            for name, value in (
                ("MULTISET_CLIENT_ID", self.client_id),
                ("MULTISET_CLIENT_SECRET", self.client_secret),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                f"MultiSet VPS is not configured: {', '.join(missing)} missing. "
                f"Add them to .env (see .env.example) or pass them to VPSSettings(...)."
            )
        assert self.client_id and self.client_secret
        return self.client_id, self.client_secret

    def require_map(
        self, map_code: str | None = None, map_ids: list[str] | None = None
    ) -> dict[str, str]:
        """The map fields for one request, as the API spells them.

        Per-call first, then the setting. Returns {"mapCode": ...} or
        {"mapIds": ...}.
        """
        if map_ids:
            return {"mapIds": json.dumps(list(map_ids))}
        code = map_code or self.map_code
        if not code:
            raise ConfigError(
                "no map to query: pass map_code= (or map_ids=) to the call, or set "
                "MULTISET_MAP_CODE in .env."
            )
        return {"mapCode": code}

    def redacted(self) -> dict[str, object]:
        """A dict safe to log: secrets become lengths, not values."""

        def mask(value: str | None) -> str:
            return f"<set, {len(value)} chars>" if value else "<unset>"

        return {
            "client_id": mask(self.client_id),
            "client_secret": mask(self.client_secret),
            "map_code": self.map_code,
            "query_mode": self.query_mode,
            "api_base": self.api_base,
        }


__all__ = [
    "DEFAULT_API_BASE",
    "REGION_API_BASES",
    "api_base_for_client_id",
    "region_for_client_id",
    "VPSSettings",
    "env_value",
    "find_env_file",
    "parse_env_file",
]
