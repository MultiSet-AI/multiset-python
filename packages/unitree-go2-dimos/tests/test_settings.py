from __future__ import annotations

import pytest
from multiset.unitree.go2.dimos import ConfigError, Go2Settings


def test_real_environment_beats_the_file(tmp_path, monkeypatch):
    """GO2_IP=... python app.py must work without editing anything."""
    env = tmp_path / ".env"
    env.write_text("GO2_IP=1.1.1.1\n")
    monkeypatch.setenv("GO2_IP", "2.2.2.2")
    assert Go2Settings.from_env(env).robot_ip == "2.2.2.2"


def test_explicit_overrides_beat_everything(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("GO2_IP=1.1.1.1\n")
    monkeypatch.setenv("GO2_IP", "2.2.2.2")
    assert Go2Settings.from_env(env, robot_ip="3.3.3.3").robot_ip == "3.3.3.3"


def test_require_robot_explains_itself():
    with pytest.raises(ConfigError, match="GO2_IP"):
        Go2Settings().require_robot()


def test_require_robot_warns_about_the_jetson():
    """The two-computer trap is the expensive one, so the error carries it."""
    with pytest.raises(ConfigError, match="9991"):
        Go2Settings().require_robot()


def test_vps_credentials_are_not_here(tmp_path):
    """The split is the point: a capture-only script must not need a map code."""
    env = tmp_path / ".env"
    env.write_text("GO2_IP=1.1.1.1\nMULTISET_MAP_CODE=MAP_X\n")
    settings = Go2Settings.from_env(env)
    assert not hasattr(settings, "map_code")
    assert settings.require_robot() == "1.1.1.1"


def test_redacted_never_leaks_the_key():
    settings = Go2Settings(aes_key="0123456789abcdef")
    dumped = str(settings.redacted())
    assert "0123456789abcdef" not in dumped
    assert "<set, 16 chars>" in dumped


def test_repr_never_leaks_the_key():
    assert "0123456789abcdef" not in repr(Go2Settings(aes_key="0123456789abcdef"))
