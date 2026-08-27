"""save_to_env writes a secret, so what it leaves on disk is part of the contract."""

from __future__ import annotations

import stat
import sys

import pytest
from multiset.unitree.go2 import Credentials, save_to_env


def _creds() -> Credentials:
    return Credentials(
        serial="B42D2000XXXXXXXX",
        aes_key="0123456789abcdef",
        alias="dog",
        model="Go2",
        online=True,
    )


def test_writes_both_keys(tmp_path):
    target = save_to_env(_creds(), tmp_path / ".env")
    body = target.read_text()
    assert "GO2_SN=B42D2000XXXXXXXX" in body
    assert "GO2_AES_KEY=0123456789abcdef" in body


def test_replaces_rather_than_appends(tmp_path):
    env = tmp_path / ".env"
    env.write_text("GO2_IP=1.1.1.1\nGO2_AES_KEY=stale\n")
    body = save_to_env(_creds(), env).read_text()
    assert "stale" not in body
    assert body.count("GO2_AES_KEY=") == 1
    assert "GO2_IP=1.1.1.1" in body, "unrelated settings must survive"


@pytest.mark.skipif(sys.platform == "win32", reason="no POSIX file modes")
def test_the_file_is_not_world_readable(tmp_path):
    """The AES key is a secret; the default umask would usually leave it 0644."""
    target = save_to_env(_creds(), tmp_path / ".env")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="no POSIX file modes")
def test_permissions_are_tightened_on_an_existing_loose_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("GO2_IP=1.1.1.1\n")
    env.chmod(0o644)
    assert stat.S_IMODE(save_to_env(_creds(), env).stat().st_mode) == 0o600
