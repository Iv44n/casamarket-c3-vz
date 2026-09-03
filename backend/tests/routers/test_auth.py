import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.auth import rate_limit, security, store
from app.benchmarks import state as benchmark_state
from app.config import AuthConfig
from app.extraction import state
from app.main import app

_AUTH_CONFIG = AuthConfig(jwt_secret="test-secret-that-is-long-enough-1234", bootstrap_username=None, bootstrap_password=None)


@pytest.fixture(autouse=True)
def clean_rate_limit_state():
    # Estado global de proceso (ver rate_limit.py) -- sin esto, tests que fallan login con el
    # mismo username ("ana") en distintas funciones de este archivo se acumularian entre si y
    # eventualmente dispararian 429 en un test que no lo espera.
    rate_limit._failed_attempts.clear()
    yield
    rate_limit._failed_attempts.clear()


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
    # lifespan tambien llama benchmark_state.reconcile_startup_state(), que pega contra
    # extraction.store.get_connection() (Turso real) -- no-opeada aca, no es lo que este
    # archivo prueba.
    monkeypatch.setattr(benchmark_state, "reconcile_startup_state", lambda: None)
    with TestClient(app) as c:
        yield c


def _bearer(user_id: int, username: str, is_admin: bool) -> dict:
    token, _ = security.create_access_token(user_id, username, is_admin, _AUTH_CONFIG.jwt_secret)
    return {"Authorization": f"Bearer {token}"}


def _admin_bearer(username: str = "admin") -> dict:
    """require_admin() re-verifica is_admin contra la DB (no confia solo en el claim del JWT) --
    a diferencia de _bearer(), esto crea una cuenta real para que esa verificacion pase."""
    user = store.create_user(
        store.get_connection(),
        username,
        security.hash_password("s3cret"),
        is_admin=True,
        created_at="2026-08-27T00:00:00",
    )
    return _bearer(user.id, user.username, True)


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


def test_login_returns_429_after_too_many_failed_attempts(client: TestClient):
    store.create_user(
        store.get_connection(), "ana", security.hash_password("s3cret"), False, "2026-08-27T00:00:00"
    )

    for _ in range(rate_limit._MAX_ATTEMPTS):
        response = client.post("/auth/login", json={"username": "ana", "password": "wrong"})
        assert response.status_code == 401

    response = client.post("/auth/login", json={"username": "ana", "password": "wrong"})

    assert response.status_code == 429


def test_login_rate_limit_is_per_username_not_global(client: TestClient):
    store.create_user(
        store.get_connection(), "ana", security.hash_password("s3cret"), False, "2026-08-27T00:00:00"
    )
    store.create_user(
        store.get_connection(), "luis", security.hash_password("s3cret"), False, "2026-08-27T00:00:00"
    )
    for _ in range(rate_limit._MAX_ATTEMPTS):
        client.post("/auth/login", json={"username": "ana", "password": "wrong"})

    response = client.post("/auth/login", json={"username": "luis", "password": "s3cret"})

    assert response.status_code == 200


def test_login_success_clears_the_failed_attempt_counter(client: TestClient):
    store.create_user(
        store.get_connection(), "ana", security.hash_password("s3cret"), False, "2026-08-27T00:00:00"
    )
    for _ in range(rate_limit._MAX_ATTEMPTS - 1):
        client.post("/auth/login", json={"username": "ana", "password": "wrong"})

    success = client.post("/auth/login", json={"username": "ana", "password": "s3cret"})
    assert success.status_code == 200

    # Si el contador no se hubiera limpiado, este intento (el _MAX_ATTEMPTS-esimo fallo
    # acumulado si se contara el de arriba) ya estaria bloqueado.
    retry = client.post("/auth/login", json={"username": "ana", "password": "wrong"})
    assert retry.status_code == 401


def test_protected_endpoint_without_authorization_header_returns_401(client: TestClient):
    response = client.get("/extraction/status")

    assert response.status_code == 401


def test_protected_endpoint_with_a_valid_bearer_token_succeeds(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    # state.last_run() real pega contra extraction.store.get_connection() (Turso real) la
    # primera vez que se llama en el proceso, via _hydrate_once() -- nada de esto es sobre auth
    # (lo unico que este test quiere probar es que un token valido pasa el Depends), asi que se
    # mockea igual que ya hacen tests/routers/test_runs.py -- confirmado en vivo el 2026-08-31
    # que sin esto el test peor caso se cuelga (o tarda decenas de segundos) contra la Turso
    # real en vez de nunca tocar la red.
    monkeypatch.setattr(state, "last_run", lambda: None)
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


def test_require_admin_rejects_a_forged_claim_for_a_non_admin_account(client: TestClient):
    """require_admin() re-verifica is_admin contra la DB -- un token con is_admin=true no
    alcanza si la cuenta real ya no es (o nunca fue) admin, cerrando la ventana en la que un
    admin degradado seguiria pudiendo usar /auth/users con su token viejo hasta que expire."""
    store.create_user(
        store.get_connection(),
        "ana",
        security.hash_password("s3cret"),
        is_admin=False,
        created_at="2026-08-27T00:00:00",
    )
    headers = _bearer(1, "ana", True)

    response = client.post(
        "/auth/users", json={"username": "luis", "password": "s3cret"}, headers=headers
    )

    assert response.status_code == 403


def test_list_users_without_admin_token_returns_403(client: TestClient):
    headers = _bearer(1, "ana", False)

    response = client.get("/auth/users", headers=headers)

    assert response.status_code == 403


def test_list_users_with_admin_token_returns_every_account(client: TestClient):
    admin_headers = _admin_bearer()
    client.post(
        "/auth/users", json={"username": "luis", "password": "s3cret"}, headers=admin_headers
    )

    response = client.get("/auth/users", headers=admin_headers)

    assert response.status_code == 200
    usernames = [u["username"] for u in response.json()]
    assert usernames == ["admin", "luis"]


def test_create_user_without_admin_token_returns_403(client: TestClient):
    headers = _bearer(1, "ana", False)

    response = client.post(
        "/auth/users", json={"username": "luis", "password": "s3cret"}, headers=headers
    )

    assert response.status_code == 403


def test_create_user_with_admin_token_returns_201(client: TestClient):
    headers = _admin_bearer()

    response = client.post(
        "/auth/users", json={"username": "luis", "password": "s3cret"}, headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "luis"
    assert body["is_admin"] is False


def test_create_user_with_a_duplicate_username_returns_409(client: TestClient):
    headers = _admin_bearer()
    client.post("/auth/users", json={"username": "luis", "password": "s3cret"}, headers=headers)

    response = client.post(
        "/auth/users", json={"username": "luis", "password": "other"}, headers=headers
    )

    assert response.status_code == 409
