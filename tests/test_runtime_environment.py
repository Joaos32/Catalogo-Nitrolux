import os
from unittest.mock import Mock

from catalog import bootstrap


def test_local_database_configuration_overrides_base_dotenv(monkeypatch, tmp_path):
    monkeypatch.setenv("CATALOG_SKIP_DOTENV", "false")
    monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", "placeholder")
    monkeypatch.delenv("CATALOG_STATE_DATABASE_URL")
    (tmp_path / ".env").write_text("CATALOG_STATE_DATABASE_URL=postgresql://base-example\n")
    (tmp_path / ".env.local").write_text("CATALOG_STATE_DATABASE_URL=postgresql://local-example\n")

    bootstrap._load_runtime_environment(tmp_path)

    assert os.environ["CATALOG_STATE_DATABASE_URL"] == "postgresql://local-example"


def test_process_database_configuration_has_priority_over_dotenv(monkeypatch, tmp_path):
    monkeypatch.setenv("CATALOG_SKIP_DOTENV", "false")
    monkeypatch.setenv("CATALOG_STATE_DATABASE_URL", "postgresql://process-example")
    (tmp_path / ".env.local").write_text("CATALOG_STATE_DATABASE_URL=postgresql://local-example\n")

    bootstrap._load_runtime_environment(tmp_path)

    assert os.environ["CATALOG_STATE_DATABASE_URL"] == "postgresql://process-example"


def test_serverless_environment_can_skip_local_dotenv(monkeypatch, tmp_path):
    monkeypatch.setenv("CATALOG_SKIP_DOTENV", "true")
    loader = Mock(side_effect=AssertionError("Unexpected local environment read"))
    monkeypatch.setattr(bootstrap, "load_dotenv", loader)

    bootstrap._load_runtime_environment(tmp_path)

    loader.assert_not_called()
