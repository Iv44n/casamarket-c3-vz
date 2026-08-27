import sqlite3

import pytest

from app.auth import store
from app.config import AuthConfig


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    store._init_schema(conn)
    return conn


def test_create_user_then_get_by_username_returns_the_same_user():
    conn = _conn()

    created = store.create_user(conn, "ana", "hash123", is_admin=True, created_at="2026-08-27T00:00:00")

    fetched = store.get_user_by_username(conn, "ana")
    assert fetched == created
    assert fetched.is_admin is True


def test_get_user_by_username_returns_none_when_not_found():
    conn = _conn()

    assert store.get_user_by_username(conn, "ghost") is None


def test_get_user_by_username_is_case_insensitive():
    conn = _conn()
    store.create_user(conn, "Ana", "hash123", is_admin=False, created_at="2026-08-27T00:00:00")

    assert store.get_user_by_username(conn, "ANA") is not None
    assert store.get_user_by_username(conn, "ana") is not None


def test_create_user_raises_username_taken_error_for_a_duplicate():
    conn = _conn()
    store.create_user(conn, "ana", "hash123", is_admin=False, created_at="2026-08-27T00:00:00")

    with pytest.raises(store.UsernameTakenError):
        store.create_user(conn, "ana", "hash456", is_admin=False, created_at="2026-08-27T00:00:00")


def test_create_user_raises_username_taken_error_for_different_casing():
    conn = _conn()
    store.create_user(conn, "Ana", "hash123", is_admin=False, created_at="2026-08-27T00:00:00")

    with pytest.raises(store.UsernameTakenError):
        store.create_user(conn, "ana", "hash456", is_admin=False, created_at="2026-08-27T00:00:00")


def test_count_users_reflects_the_number_of_created_accounts():
    conn = _conn()
    assert store.count_users(conn) == 0

    store.create_user(conn, "ana", "hash123", is_admin=False, created_at="2026-08-27T00:00:00")
    store.create_user(conn, "luis", "hash456", is_admin=False, created_at="2026-08-27T00:00:00")

    assert store.count_users(conn) == 2


def test_seed_bootstrap_admin_creates_the_account_when_table_is_empty():
    conn = _conn()
    auth_config = AuthConfig(
        jwt_secret="shh", bootstrap_username="admin", bootstrap_password="s3cret"
    )

    seeded = store.seed_bootstrap_admin(conn, auth_config, "2026-08-27T00:00:00")

    assert seeded is not None
    assert seeded.username == "admin"
    assert seeded.is_admin is True
    stored = store.get_user_by_username(conn, "admin")
    assert stored.password_hash != "s3cret"  # nunca se guarda en texto plano


def test_seed_bootstrap_admin_is_a_noop_when_a_user_already_exists():
    conn = _conn()
    store.create_user(conn, "ana", "hash123", is_admin=False, created_at="2026-08-27T00:00:00")
    auth_config = AuthConfig(
        jwt_secret="shh", bootstrap_username="admin", bootstrap_password="s3cret"
    )

    seeded = store.seed_bootstrap_admin(conn, auth_config, "2026-08-27T00:00:00")

    assert seeded is None
    assert store.count_users(conn) == 1


def test_seed_bootstrap_admin_is_a_noop_when_bootstrap_env_vars_are_missing():
    conn = _conn()
    auth_config = AuthConfig(jwt_secret="shh", bootstrap_username=None, bootstrap_password=None)

    seeded = store.seed_bootstrap_admin(conn, auth_config, "2026-08-27T00:00:00")

    assert seeded is None
    assert store.count_users(conn) == 0
