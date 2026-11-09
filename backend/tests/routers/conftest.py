import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.auth import security
from app.auth import store as auth_store
from app.benchmarks import state as benchmark_state
from app.config import AuthConfig
from app.extraction import state as extraction_state
from app.incidents import store as incidents_store
from app.main import app

_AUTH_CONFIG = AuthConfig(
    jwt_secret="test-secret-that-is-long-enough-1234",
    bootstrap_username=None,
    bootstrap_password=None,
)


@dataclass
class Api:
    """Cliente con autenticacion REAL (tokens firmados + tabla users en sqlite), a diferencia de
    los fixtures `client` de test_data/test_runs/test_benchmarks que overridean las
    dependencias de auth -- aca lo que se prueba es justamente el gating por rol."""

    client: TestClient

    def create_user(self, username: str, role: str) -> auth_store.UserRecord:
        conn = auth_store.get_connection()
        try:
            return auth_store.create_user(
                conn, username, security.hash_password("s3cret"), role, "2026-11-09T00:00:00"
            )
        finally:
            conn.close()

    def headers_for(self, user: auth_store.UserRecord, role_claim: str | None = None) -> dict:
        token, _ = security.create_access_token(
            user.id, user.username, role_claim or user.role, _AUTH_CONFIG.jwt_secret
        )
        return {"Authorization": f"Bearer {token}"}

    def user_headers(self, username: str, role: str) -> dict:
        return self.headers_for(self.create_user(username, role))


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    auth_db = tmp_path / "auth.db"
    incidents_db = tmp_path / "incidents.db"

    def _auth_connection() -> sqlite3.Connection:
        conn = sqlite3.connect(str(auth_db), check_same_thread=False)
        auth_store._init_schema(conn)
        return conn

    def _incidents_connection() -> sqlite3.Connection:
        conn = sqlite3.connect(str(incidents_db), check_same_thread=False)
        incidents_store._init_schema(conn)
        return conn

    monkeypatch.setattr(auth_store, "get_connection", _auth_connection)
    monkeypatch.setattr(incidents_store, "get_connection", _incidents_connection)
    monkeypatch.setattr(config, "load_auth_config", lambda: _AUTH_CONFIG)
    # lifespan y /extraction/status tocarian la Turso real -- no es lo que se prueba aca.
    monkeypatch.setattr(benchmark_state, "reconcile_startup_state", lambda: None)
    monkeypatch.setattr(extraction_state, "last_run", lambda: None)
    with TestClient(app) as client:
        yield Api(client)
