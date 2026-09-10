"""Settings: the same precedence rules as every other device package."""

from __future__ import annotations

import dataclasses

import pytest
from multiset.insta360 import Insta360Error, Insta360Settings


def test_real_environment_beats_the_file(tmp_path, monkeypatch):
    """INSTA360_SSH_HOST=... python app.py must work without editing anything."""
    env = tmp_path / ".env"
    env.write_text("INSTA360_SSH_HOST=unitree@1.1.1.1\n")
    monkeypatch.setenv("INSTA360_SSH_HOST", "unitree@2.2.2.2")
    assert Insta360Settings.from_env(env).ssh_host == "unitree@2.2.2.2"


def test_explicit_overrides_beat_everything(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("INSTA360_SSH_HOST=unitree@1.1.1.1\n")
    monkeypatch.setenv("INSTA360_SSH_HOST", "unitree@2.2.2.2")
    settings = Insta360Settings.from_env(env, ssh_host="unitree@3.3.3.3")
    assert settings.ssh_host == "unitree@3.3.3.3"


def test_the_device_defaults_without_an_env_file(tmp_path):
    assert Insta360Settings.from_env(tmp_path / "nope.env").device == "/dev/video0"


def test_a_missing_host_explains_both_options(tmp_path, monkeypatch):
    """The fix is a host or UsbCamera -- name both."""
    monkeypatch.delenv("INSTA360_SSH_HOST", raising=False)
    settings = Insta360Settings.from_env(tmp_path / "nope.env")
    with pytest.raises(Insta360Error, match="UsbCamera"):
        settings.require_ssh_host()


def test_settings_are_frozen():
    """A value, so nothing mutates it behind a caller's back."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        Insta360Settings().ssh_host = "x"  # type: ignore[misc]
