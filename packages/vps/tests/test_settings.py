from __future__ import annotations

import pytest
from multiset.vps import ConfigError, VPSSettings
from multiset.vps.settings import parse_env_file


def test_parse_env_file_ignores_comments_and_blanks(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# a comment\n\nGO2_IP=10.0.0.5\n  GO2_SN = B42  \nnot_a_pair\n")
    assert parse_env_file(env) == {"GO2_IP": "10.0.0.5", "GO2_SN": "B42"}


def test_parse_env_file_missing_is_empty(tmp_path):
    assert parse_env_file(tmp_path / "nope.env") == {}


def test_real_environment_beats_the_file(tmp_path, monkeypatch):
    """MULTISET_MAP_CODE=... python app.py must work without editing anything."""
    env = tmp_path / ".env"
    env.write_text("MULTISET_MAP_CODE=MAP_FROMFILE\n")
    monkeypatch.setenv("MULTISET_MAP_CODE", "MAP_FROMENV")
    assert VPSSettings.from_env(env).map_code == "MAP_FROMENV"


def test_explicit_overrides_beat_everything(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("MULTISET_MAP_CODE=MAP_FROMFILE\n")
    monkeypatch.setenv("MULTISET_MAP_CODE", "MAP_FROMENV")
    assert VPSSettings.from_env(env, map_code="MAP_EXPLICIT").map_code == "MAP_EXPLICIT"


def test_require_auth_names_every_missing_key():
    with pytest.raises(ConfigError) as excinfo:
        VPSSettings(client_id="x").require_auth()
    message = str(excinfo.value)
    assert "MULTISET_CLIENT_SECRET" in message
    assert "MULTISET_CLIENT_ID" not in message  # that one was supplied


def test_require_auth_does_not_demand_a_map_code():
    """Auth is all a client needs to exist; the map belongs to the call.

    Map listing, status and upload need credentials and no map code, and used
    to be blocked at construction because require() demanded all three.
    """
    assert VPSSettings(client_id="x", client_secret="y").require_auth() == ("x", "y")


def test_redacted_never_leaks_a_secret():
    settings = VPSSettings(client_secret="supersecretvalue")
    dumped = str(settings.redacted())
    assert "supersecretvalue" not in dumped
    assert "<set, 16 chars>" in dumped


def test_repr_never_leaks_a_secret():
    """A VPSSettings caught in a traceback must not print the customer's key."""
    assert "supersecret" not in repr(VPSSettings(client_secret="supersecret"))


def test_api_base_follows_the_client_id_region():
    assert VPSSettings(client_id="32f7fbbe-9ad1-4bc9").api_base == "https://api.multiset.ai/v1"
    assert VPSSettings(client_id="eu_32f7fbbe-9ad1-4bc9").api_base == "https://api.eu.multiset.ai/v1"
    assert VPSSettings().api_base == "https://api.multiset.ai/v1"


def test_explicit_api_base_beats_the_client_id_region(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTISET_CLIENT_ID", "eu_abc")
    monkeypatch.setenv("MULTISET_API_BASE", "https://dev-api.multiset.ai/v1")
    assert VPSSettings.from_env(tmp_path / ".env").api_base == "https://dev-api.multiset.ai/v1"


def test_client_id_override_picks_its_region(tmp_path, monkeypatch):
    monkeypatch.delenv("MULTISET_API_BASE", raising=False)
    monkeypatch.setenv("MULTISET_CLIENT_ID", "us-client")
    settings = VPSSettings.from_env(tmp_path / ".env", client_id="eu_abc")
    assert settings.api_base == "https://api.eu.multiset.ai/v1"
