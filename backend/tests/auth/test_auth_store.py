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

    created = store.create_user(conn, "ana", "hash123", role="admin", created_at="2026-08-27T00:00:00")

    fetched = store.get_user_by_username(conn, "ana")
    assert fetched == created
    assert fetched.is_admin is True


def test_get_user_by_username_returns_none_when_not_found():
    conn = _conn()

    assert store.get_user_by_username(conn, "ghost") is None


def test_get_user_by_username_is_case_insensitive():
    conn = _conn()
    store.create_user(conn, "Ana", "hash123", role="user", created_at="2026-08-27T00:00:00")

    assert store.get_user_by_username(conn, "ANA") is not None
    assert store.get_user_by_username(conn, "ana") is not None


def test_create_user_raises_username_taken_error_for_a_duplicate():
    conn = _conn()
    store.create_user(conn, "ana", "hash123", role="user", created_at="2026-08-27T00:00:00")

    with pytest.raises(store.UsernameTakenError):
        store.create_user(conn, "ana", "hash456", role="user", created_at="2026-08-27T00:00:00")


def test_create_user_raises_username_taken_error_for_different_casing():
    conn = _conn()
    store.create_user(conn, "Ana", "hash123", role="user", created_at="2026-08-27T00:00:00")

    with pytest.raises(store.UsernameTakenError):
        store.create_user(conn, "ana", "hash456", role="user", created_at="2026-08-27T00:00:00")


def test_count_users_reflects_the_number_of_created_accounts():
    conn = _conn()
    assert store.count_users(conn) == 0

    store.create_user(conn, "ana", "hash123", role="user", created_at="2026-08-27T00:00:00")
    store.create_user(conn, "luis", "hash456", role="user", created_at="2026-08-27T00:00:00")

    assert store.count_users(conn) == 2


def test_list_users_returns_every_account_ordered_by_id():
    conn = _conn()
    store.create_user(conn, "luis", "hash456", role="user", created_at="2026-08-27T00:00:00")
    store.create_user(conn, "ana", "hash123", role="admin", created_at="2026-08-27T00:00:01")

    users = store.list_users(conn)

    assert [u.username for u in users] == ["luis", "ana"]
    assert [u.is_admin for u in users] == [False, True]


def test_list_users_returns_an_empty_list_when_no_accounts_exist():
    conn = _conn()

    assert store.list_users(conn) == []


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
    store.create_user(conn, "ana", "hash123", role="user", created_at="2026-08-27T00:00:00")
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


def test_create_user_with_the_incidents_role_is_not_admin():
    conn = _conn()

    user = store.create_user(conn, "rosa", "hash", role="incidencias", created_at="2026-11-09T00:00:00")

    assert user.role == "incidencias"
    assert user.is_admin is False
    # is_admin se sigue escribiendo en sincronia con role (compatibilidad con codigo viejo).
    assert conn.execute("SELECT is_admin FROM users WHERE id = ?", (user.id,)).fetchone()[0] == 0


def test_create_user_rejects_an_unknown_role():
    conn = _conn()

    with pytest.raises(ValueError):
        store.create_user(conn, "rosa", "hash", role="superuser", created_at="2026-11-09T00:00:00")


def test_migration_backfills_role_from_is_admin_on_a_pre_existing_users_table():
    conn = sqlite3.connect(":memory:")
    # Shape de la tabla antes de que existiera `role` (Turso en vivo).
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        INSERT INTO users (username, password_hash, is_admin, created_at)
            VALUES ('boss', 'h', 1, '2026-08-27T00:00:00'), ('ana', 'h', 0, '2026-08-27T00:00:00');
        """
    )

    store._init_schema(conn)
    store._init_schema(conn)  # idempotente: la segunda corrida no toca nada

    assert [(u.username, u.role) for u in store.list_users(conn)] == [
        ("boss", "admin"),
        ("ana", "user"),
    ]


def test_update_user_changes_role_and_keeps_is_admin_in_sync():
    conn = _conn()
    store.create_user(conn, "boss", "h", role="admin", created_at="2026-11-09T00:00:00")
    ana = store.create_user(conn, "ana", "h", role="user", created_at="2026-11-09T00:00:00")

    promoted = store.update_user(conn, ana.id, role="admin")
    assert promoted is not None and promoted.role == "admin"
    assert conn.execute("SELECT is_admin FROM users WHERE id = ?", (ana.id,)).fetchone()[0] == 1

    restricted = store.update_user(conn, ana.id, role="incidencias")
    assert restricted is not None and restricted.role == "incidencias"
    assert conn.execute("SELECT is_admin FROM users WHERE id = ?", (ana.id,)).fetchone()[0] == 0


def test_update_user_renames_normalizing_and_changes_password():
    conn = _conn()
    ana = store.create_user(conn, "ana", "old-hash", role="user", created_at="2026-11-09T00:00:00")

    updated = store.update_user(conn, ana.id, username="  Ana.Perez ", password_hash="new-hash")

    assert updated is not None
    assert updated.username == "ana.perez"
    assert updated.password_hash == "new-hash"
    assert updated.role == "user"
    assert store.get_user_by_username(conn, "ana") is None


def test_update_user_rejects_a_username_owned_by_another_account():
    conn = _conn()
    store.create_user(conn, "luis", "h", role="user", created_at="2026-11-09T00:00:00")
    ana = store.create_user(conn, "ana", "h", role="user", created_at="2026-11-09T00:00:00")

    with pytest.raises(store.UsernameTakenError):
        store.update_user(conn, ana.id, username="LUIS")


def test_update_user_keeping_the_same_username_with_other_casing_is_not_a_conflict():
    conn = _conn()
    ana = store.create_user(conn, "ana", "h", role="user", created_at="2026-11-09T00:00:00")

    assert store.update_user(conn, ana.id, username="ANA").username == "ana"


def test_update_user_refuses_to_remove_the_last_admin():
    conn = _conn()
    boss = store.create_user(conn, "boss", "h", role="admin", created_at="2026-11-09T00:00:00")

    with pytest.raises(store.LastAdminError):
        store.update_user(conn, boss.id, role="user")

    assert store.get_user_by_id(conn, boss.id).role == "admin"


def test_update_user_returns_none_for_an_unknown_user():
    conn = _conn()

    assert store.update_user(conn, 999, role="user") is None


def test_delete_user_removes_the_account():
    conn = _conn()
    store.create_user(conn, "boss", "h", role="admin", created_at="2026-11-09T00:00:00")
    ana = store.create_user(conn, "ana", "h", role="user", created_at="2026-11-09T00:00:00")

    assert store.delete_user(conn, ana.id) is True

    assert store.get_user_by_id(conn, ana.id) is None
    assert store.delete_user(conn, ana.id) is False


def test_delete_user_refuses_to_delete_the_last_admin_but_allows_one_of_two():
    conn = _conn()
    boss = store.create_user(conn, "boss", "h", role="admin", created_at="2026-11-09T00:00:00")
    second = store.create_user(conn, "jefa", "h", role="admin", created_at="2026-11-09T00:00:00")

    assert store.delete_user(conn, second.id) is True
    with pytest.raises(store.LastAdminError):
        store.delete_user(conn, boss.id)
