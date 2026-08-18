from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app import config


@pytest.fixture(autouse=True)
def clean_credential_env(monkeypatch: pytest.MonkeyPatch):
    for key in config._CREDENTIAL_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key in config._TURSO_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_project_root_is_the_repo_root_not_app():
    assert (config.PROJECT_ROOT / "pyproject.toml").exists()
    assert config.PROJECT_ROOT.name != "app"


def test_recon_and_downloads_dirs_are_under_project_root():
    assert config.RECON_DIR.parent == config.PROJECT_ROOT
    assert config.DOWNLOADS_DIR.parent == config.PROJECT_ROOT


def test_tz_is_america_lima():
    assert config.TZ == ZoneInfo("America/Lima")


def test_hoy_returns_a_date():
    import datetime

    assert isinstance(config.hoy(), datetime.date)


def test_load_credentials_missing_file_raises(tmp_path: Path):
    with pytest.raises(RuntimeError, match="C3_USERNAME"):
        config.load_credentials(env_path=tmp_path / "no-existe.env")


def test_load_credentials_missing_password_raises(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("C3_USERNAME=alguien\n")

    with pytest.raises(RuntimeError, match="C3_PASSWORD"):
        config.load_credentials(env_path=env_file)


def test_load_credentials_success(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "C3_USERNAME=alguien\nC3_PASSWORD=secreta\nC3_BASE_URL=https://otro.example\n"
    )

    creds = config.load_credentials(env_path=env_file)

    assert creds.username == "alguien"
    assert creds.password == "secreta"
    assert creds.base_url == "https://otro.example"


def test_load_credentials_base_url_defaults_when_absent(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("C3_USERNAME=alguien\nC3_PASSWORD=secreta\n")

    creds = config.load_credentials(env_path=env_file)

    assert creds.base_url == config.BASE_URL


def test_load_credentials_reads_from_process_env_when_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("C3_USERNAME", "envuser")
    monkeypatch.setenv("C3_PASSWORD", "envpass")

    creds = config.load_credentials(env_path=tmp_path / "no-existe.env")

    assert creds.username == "envuser"
    assert creds.password == "envpass"
    assert creds.base_url == config.BASE_URL


def test_load_credentials_process_env_overrides_file_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    env_file = tmp_path / ".env"
    env_file.write_text("C3_USERNAME=fileuser\nC3_PASSWORD=filepass\n")
    monkeypatch.setenv("C3_PASSWORD", "envpass")

    creds = config.load_credentials(env_path=env_file)

    assert creds.username == "fileuser"
    assert creds.password == "envpass"


def test_load_credentials_base_url_from_process_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("C3_USERNAME", "envuser")
    monkeypatch.setenv("C3_PASSWORD", "envpass")
    monkeypatch.setenv("C3_BASE_URL", "https://from-env.example")

    creds = config.load_credentials(env_path=tmp_path / "no-existe.env")

    assert creds.base_url == "https://from-env.example"


def test_load_turso_config_missing_file_raises(tmp_path: Path):
    with pytest.raises(RuntimeError, match="TURSO_DATABASE_URL"):
        config.load_turso_config(env_path=tmp_path / "no-existe.env")


def test_load_turso_config_missing_token_raises(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("TURSO_DATABASE_URL=libsql://x.turso.io\n")

    with pytest.raises(RuntimeError, match="TURSO_AUTH_TOKEN"):
        config.load_turso_config(env_path=env_file)


def test_load_turso_config_success(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TURSO_DATABASE_URL=libsql://x.turso.io\nTURSO_AUTH_TOKEN=secreto\n"
    )

    turso = config.load_turso_config(env_path=env_file)

    assert turso.database_url == "libsql://x.turso.io"
    assert turso.auth_token == "secreto"


def test_load_turso_config_reads_from_process_env_when_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://env.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "envtoken")

    turso = config.load_turso_config(env_path=tmp_path / "no-existe.env")

    assert turso.database_url == "libsql://env.turso.io"
    assert turso.auth_token == "envtoken"
