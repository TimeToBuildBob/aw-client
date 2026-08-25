"""Client constructor, config sections, persistqueue, and rust api-key lookup."""

import os

import pytest

from aw_client import ActivityWatchClient
from aw_client import client as client_module
from aw_client.config import load_local_server_api_key
from aw_client.profile import DEFAULT_PROFILE, TESTING_PROFILE


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.delenv("AW_PROFILE", raising=False)
    monkeypatch.setattr(client_module, "SingleInstance", lambda name: object())
    return tmp_path


class TestClientConstructor:
    def test_testing_alias_uses_testing_port_and_exports_env(self, isolated_dirs):
        client = ActivityWatchClient("t", testing=True)
        assert client.profile == TESTING_PROFILE
        assert client.testing is True
        assert client.server_address.endswith(":5666")
        assert os.environ["AW_PROFILE"] == "testing"

    def test_explicit_profile_testing_is_the_same(self, isolated_dirs):
        client = ActivityWatchClient("t", profile="testing")
        assert client.profile == TESTING_PROFILE
        assert client.testing is True
        assert client.server_address.endswith(":5666")

    def test_default_unsets_env_and_uses_5600(self, isolated_dirs, monkeypatch):
        monkeypatch.setenv("AW_PROFILE", "research")
        client = ActivityWatchClient("t", profile="default")
        assert client.profile == DEFAULT_PROFILE
        assert client.testing is False
        assert client.server_address.endswith(":5600")
        assert "AW_PROFILE" not in os.environ

    def test_named_profile_falls_back_to_server_section(self, isolated_dirs):
        client = ActivityWatchClient("t", profile="research")
        assert client.profile == "research"
        assert client.testing is False
        assert client.server_address.endswith(":5600")
        assert os.environ["AW_PROFILE"] == "research"

    def test_env_from_launcher_is_used_when_no_flags(self, isolated_dirs, monkeypatch):
        monkeypatch.setenv("AW_PROFILE", "research")
        client = ActivityWatchClient("t")
        assert client.profile == "research"
        assert os.environ["AW_PROFILE"] == "research"

    def test_explicit_testing_overrides_stale_env(self, isolated_dirs, monkeypatch):
        monkeypatch.setenv("AW_PROFILE", "research")
        client = ActivityWatchClient("t", testing=True)
        assert client.profile == TESTING_PROFILE
        assert os.environ["AW_PROFILE"] == "testing"

    def test_host_and_port_kwargs_still_win(self, isolated_dirs):
        client = ActivityWatchClient(
            "t", profile="research", host="127.0.0.1", port=5667
        )
        assert client.server_address == "http://127.0.0.1:5667"

    def test_conflicting_flags_raise(self, isolated_dirs):
        with pytest.raises(ValueError, match="conflicts"):
            ActivityWatchClient("t", testing=True, profile="research")


class TestPersistqueueSuffix:
    def test_testing_keeps_legacy_suffix(self, isolated_dirs):
        client = ActivityWatchClient("aw-test-client", testing=True)
        assert "aw-test-client-testing." in client.request_queue.persistqueue_path

    def test_named_profile_suffix_is_disjoint(self, isolated_dirs):
        testing = ActivityWatchClient("aw-test-client", testing=True)
        research = ActivityWatchClient("aw-test-client", profile="research")
        assert (
            testing.request_queue.persistqueue_path
            != research.request_queue.persistqueue_path
        )
        assert "aw-test-client-research." in research.request_queue.persistqueue_path


def test_load_local_server_api_key_named_profile(tmp_path, monkeypatch):
    # Patch get_config_dir rather than XDG_CONFIG_HOME — platformdirs on
    # macOS/Windows ignores XDG_* even when set.
    monkeypatch.setattr(
        "aw_client.config.dirs.get_config_dir",
        lambda module: str(tmp_path / module),
    )
    rust_dir = tmp_path / "aw-server-rust"
    rust_dir.mkdir()
    (rust_dir / "config-research.toml").write_text(
        'port = 5667\n\n[auth]\napi_key = "research-secret"\n'
    )
    (rust_dir / "config.toml").write_text(
        'port = 5600\n\n[auth]\napi_key = "default-secret"\n'
    )
    assert (
        load_local_server_api_key("127.0.0.1", 5667, profile="research")
        == "research-secret"
    )
    assert load_local_server_api_key("127.0.0.1", 5600, profile="default") == (
        "default-secret"
    )
    assert load_local_server_api_key("127.0.0.1", 5600, profile="research") is None


class TestCliPortOverride:
    def test_explicit_port_5600_is_not_discarded(self, monkeypatch):
        captured = {}

        class FakeClient:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def get_buckets(self):
                return {}

        monkeypatch.setattr("aw_client.cli.aw_client.ActivityWatchClient", FakeClient)
        from click.testing import CliRunner

        from aw_client.cli import main

        result = CliRunner().invoke(main, ["--port", "5600", "buckets"])
        assert result.exit_code == 0, result.output
        assert captured["port"] == 5600

    def test_omitted_port_lets_profile_config_win(self, monkeypatch):
        captured = {}

        class FakeClient:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def get_buckets(self):
                return {}

        monkeypatch.setattr("aw_client.cli.aw_client.ActivityWatchClient", FakeClient)
        from click.testing import CliRunner

        from aw_client.cli import main

        result = CliRunner().invoke(main, ["--testing", "buckets"])
        assert result.exit_code == 0, result.output
        assert captured["port"] is None
        assert captured["testing"] is True
