"""The robot's AES key and serial, from Unitree's cloud.

Firmware >= 1.1.15 encrypts the LAN handshake and refuses the connection
without a per-device AES-128 key. That key cannot be derived or read off the
robot -- not even from its IP -- so this takes the account email and password.

Nothing here writes to disk or prompts; the CLI owns both.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from multiset.vps import ConfigError

from .errors import Go2Error

log = logging.getLogger(__name__)


# The global endpoint's WAF answers a 567 challenge to Chrome/Edge TLS
# fingerprints from some networks. Safari's passes; upstream hardcodes chrome120.
WAF_SAFE_IMPERSONATION = "safari17_0"

REGIONS = ("global", "cn")


@dataclass(frozen=True)
class Credentials:
    """One robot's identity, as the cloud knows it."""

    serial: str
    aes_key: str = field(repr=False)
    alias: str = ""
    model: str = ""
    online: bool | None = None

    @property
    def has_key(self) -> bool:
        return bool(self.aes_key)

    def redacted(self) -> str:
        key = f"<set, {len(self.aes_key)} chars>" if self.aes_key else "<none>"
        state = {True: "online", False: "offline", None: "?"}[self.online]
        return (
            f"{self.alias or '(no alias)'}  sn={self.serial}  {self.model}  {state}  key: {key}"
        )


def fetch_credentials(
    email: str, password: str, *, region: str = "global", serial: str | None = None
) -> list[Credentials]:
    """Every robot bound to a Unitree account, each with its AES key.

    Pass `serial` to get just that robot. Raises ConfigError if the account has
    no robots, or the requested serial is not bound to it.

    Needs the `cloud` extra:  pip install 'multiset-unitree-go2-dimos[cloud]'
    """
    if region not in REGIONS:
        # Upstream accepts 'cn', not 'china'; catching it here beats failing
        # after the password prompt.
        raise ConfigError(f"region must be one of {REGIONS}, got {region!r}")
    try:
        from curl_cffi import requests as cffi_requests
        from unitree_webrtc_connect.unitree_cloud import UnitreeCloud
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise Go2Error(
            "fetching the AES key needs the cloud extra:\n"
            "    pip install 'multiset-unitree-go2-dimos[cloud]'"
        ) from exc

    cloud = UnitreeCloud(region=region, device_type="Go2")
    cloud._session = cffi_requests.Session(impersonate=WAF_SAFE_IMPERSONATION)
    cloud.login_email(email, password)

    devices = [
        Credentials(
            serial=d.sn,
            aes_key=d.key or "",
            alias=d.alias or "",
            model=d.model or "",
            online=d.online,
        )
        for d in cloud.list_devices()
    ]
    if not devices:
        raise ConfigError(f"no robots are bound to {email}")
    log.info("cloud: %d robot(s) bound to the account", len(devices))

    if serial:
        match = [d for d in devices if d.serial == serial]
        if not match:
            raise ConfigError(
                f"serial {serial} is not bound to {email}; "
                f"the account has {', '.join(d.serial for d in devices)}"
            )
        return match
    return devices


def find_serial(timeout: float = 3.0) -> dict[str, str]:
    """{serial: ip} for every robot answering the Unitree multicast query.

    The only mechanism that yields the SERIAL, which is what pairs the robot in
    front of you with the right row in your cloud account. Many networks drop
    multicast, and it cannot cross a router.
    """
    try:
        from unitree_webrtc_connect.multicast_scanner import discover_ip_sn

        return discover_ip_sn(timeout=timeout) or {}
    except OSError as exc:
        log.debug("multicast unavailable: %s", exc)
        return {}
    except Exception:  # noqa: BLE001
        log.debug("multicast discovery raised", exc_info=True)
        return {}


def save_to_env(credentials: Credentials, path: str | Path = ".env") -> Path:
    """Write GO2_SN and GO2_AES_KEY into a .env, replacing any that exist.

    Returns the file written. The key never appears in a log line -- callers
    that want to confirm should print `credentials.redacted()`.

    Left mode 0600: this writes a secret, and the default umask would not.
    """
    target = Path(path)
    lines = target.read_text().splitlines() if target.exists() else []
    pairs = {"GO2_SN": credentials.serial, "GO2_AES_KEY": credentials.aes_key}
    kept = [ln for ln in lines if ln.split("=", 1)[0].strip() not in pairs]
    kept = [ln for ln in kept if ln.strip()]
    target.write_text("\n".join([*kept, *(f"{k}={v}" for k, v in pairs.items())]) + "\n")
    try:
        target.chmod(0o600)
    except OSError as exc:  # no POSIX modes -- Windows, some mounts
        log.debug("could not restrict permissions on %s: %s", target, exc)
    log.info("wrote GO2_SN and GO2_AES_KEY to %s (mode 0600)", target)
    return target


__all__ = ["REGIONS", "Credentials", "fetch_credentials", "find_serial", "save_to_env"]
