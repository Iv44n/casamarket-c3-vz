import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.auth import security, store
from app.config import AuthConfig
from app.main import app

_AUTH_CONFIG = AuthConfig(jwt_secret="test-secret-that-is-long-enough-1234", bootstrap_username=None, bootstrap_password=None)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Conexion fresca por llamada, respaldada por un archivo temporal (no ":memory:", que
    # perderia los datos entre conexiones distintas) -- mismo shape que la produccion (cada
    # get_connection() devuelve una conexion nueva que el llamador cierra). Con una unica
    # conexion compartida (como hacen otros tests de este proyecto), el conn.close() del
    # lifespan hook de main.py la dejaria inutilizable para el resto del test.
    db_path = tmp_path / "auth-test.db"

    def _get_connection() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        store._init_schema(conn)
        return conn

    monkeypatch.setattr(store, "get_connection", _get_connection)
    monkeypatch.setattr(config, "load_auth_config", lambda: _AUTH_CONFIG)
    with TestClient(app) as c:
        yield c


def _bearer(user_id: int, username: str, is_admin: bool) -> dict:
    token, _ = security.create_access_token(user_id, username, is_admin, _AUTH_CONFIG.jwt_secret)
    return {"Authorization": f"Bearer {token}"}


def test_login_with_correct_credentials_returns_a_decodable_token(client: TestClient):
    store.create_user(
        store.get_connection(), "ana", security.hash_password("s3cret"), False, "2026-08-27T00:00:00"
    )

    response = client.post("/auth/login", json={"username": "ana", "password": "s3cret"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    payload = security.decode_access_token(body["access_token"], _AUTH_CONFIG.jwt_secret)
    assert payload.username == "ana"
    assert payload.is_admin is False


def test_login_with_wrong_password_returns_401(client: TestClient):
    store.create_user(
        store.get_connection(), "ana", security.hash_password("s3cret"), False, "2026-08-27T00:00:00"
    )

    response = client.post("/auth/login", json={"username": "ana", "password": "wrong"})

    assert response.status_code == 401


def test_login_with_unknown_username_returns_401_with_the_same_message_as_wrong_password(
    client: TestClient,
):
    store.create_user(
        store.get_connection(), "ana", security.hash_password("s3cret"), False, "2026-08-27T00:00:00"
    )
    wrong_password_response = client.post(
        "/auth/login", json={"username": "ana", "password": "wrong"}
    )

    unknown_user_response = client.post(
        "/auth/login", json={"username": "ghost", "password": "wrong"}
    )

    assert unknown_user_response.status_code == 401
    assert unknown_user_response.json()["detail"] == wrong_password_response.json()["detail"]


def test_protected_endpoint_without_authorization_header_returns_401(client: TestClient):
    response = client.get("/extraction/status")

    assert response.status_code == 401


def test_protected_endpoint_with_a_valid_bearer_token_succeeds(client: TestClient):
    headers = _bearer(1, "ana", False)

    response = client.get("/extraction/status", headers=headers)

    assert response.status_code == 200


def test_me_returns_the_current_user(client: TestClient):
    store.create_user(
        store.get_connection(), "ana", security.hash_password("s3cret"), True, "2026-08-27T00:00:00"
    )
    headers = _bearer(1, "ana", True)

    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "ana"
    assert body["is_admin"] is True


def test_create_user_without_admin_token_returns_403(client: TestClient):
    headers = _bearer(1, "ana", False)

    response = client.post(
        "/auth/users", json={"username": "luis", "password": "s3cret"}, headers=headers
    )

    assert response.status_code == 403


def test_create_user_with_admin_token_returns_201(client: TestClient):
    headers = _bearer(1, "admin", True)

    response = client.post(
        "/auth/users", json={"username": "luis", "password": "s3cret"}, headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "luis"
    assert body["is_admin"] is False


def test_create_user_with_a_duplicate_username_returns_409(client: TestClient):
    headers = _bearer(1, "admin", True)
    client.post("/auth/users", json={"username": "luis", "password": "s3cret"}, headers=headers)

    response = client.post(
        "/auth/users", json={"username": "luis", "password": "other"}, headers=headers
    )

    assert response.status_code == 409
