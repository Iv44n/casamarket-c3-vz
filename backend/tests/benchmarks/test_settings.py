import sqlite3

from app.benchmarks import settings


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    settings._init_schema(conn)
    return conn


def test_load_llm_config_returns_none_when_nothing_saved_yet():
    conn = _conn()

    assert settings.load_llm_config(conn) is None


def test_save_llm_config_then_load_returns_the_same_values():
    conn = _conn()

    saved = settings.save_llm_config(
        conn, "minimax", "mm-secreta", "MiniMax-M1", "https://api.minimax.io/v1", "2026-08-27T00:00:00"
    )

    assert saved.provider_name == "minimax"
    assert saved.api_key == "mm-secreta"
    assert saved.model == "MiniMax-M1"
    assert saved.base_url == "https://api.minimax.io/v1"
    assert saved.updated_at == "2026-08-27T00:00:00"

    loaded = settings.load_llm_config(conn)
    assert loaded == saved


def test_save_llm_config_overwrites_the_previous_singleton_row():
    conn = _conn()
    settings.save_llm_config(
        conn, "minimax", "old-key", "MiniMax-M1", "https://api.minimax.io/v1", "2026-08-27T00:00:00"
    )

    settings.save_llm_config(
        conn, "minimax", "new-key", "MiniMax-M2", "https://api.minimax.io/v2", "2026-08-27T00:01:00"
    )

    loaded = settings.load_llm_config(conn)
    assert loaded.api_key == "new-key"
    assert loaded.model == "MiniMax-M2"


def test_save_llm_config_can_switch_provider_and_omit_base_url():
    conn = _conn()
    settings.save_llm_config(
        conn, "minimax", "mm-secreta", "MiniMax-M1", "https://api.minimax.io/v1", "2026-08-27T00:00:00"
    )

    updated = settings.save_llm_config(
        conn, "claude", "sk-ant-secreta", "claude-sonnet-5", None, "2026-09-11T00:00:00"
    )

    assert updated.provider_name == "claude"
    assert updated.model == "claude-sonnet-5"
    assert updated.base_url is None


def test_save_llm_config_with_api_key_none_preserves_the_existing_key():
    conn = _conn()
    settings.save_llm_config(
        conn, "minimax", "keep-me", "MiniMax-M1", "https://api.minimax.io/v1", "2026-08-27T00:00:00"
    )

    updated = settings.save_llm_config(
        conn, "minimax", None, "MiniMax-M2", "https://api.minimax.io/v1", "2026-08-27T00:01:00"
    )

    assert updated.api_key == "keep-me"
    assert updated.model == "MiniMax-M2"


def test_save_llm_config_with_api_key_none_and_nothing_saved_yet_leaves_it_empty():
    conn = _conn()

    saved = settings.save_llm_config(
        conn, "minimax", None, "MiniMax-M1", "https://api.minimax.io/v1", "2026-08-27T00:00:00"
    )

    assert saved.api_key is None


def test_migrate_generic_columns_backfills_from_a_pre_multi_provider_table():
    """Simula una tabla creada antes de que este modulo soportara mas de un proveedor (solo
    minimax_api_key/minimax_model/minimax_base_url, sin las columnas genericas) -- confirma
    que _migrate_generic_columns las agrega y copia el valor ya guardado, para que un admin
    que ya habia configurado MiniMax no pierda esa config al desplegar este cambio."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE llm_settings (
            id                INTEGER PRIMARY KEY CHECK (id = 1),
            provider_name     TEXT NOT NULL,
            minimax_api_key   TEXT,
            minimax_model     TEXT,
            minimax_base_url  TEXT,
            updated_at        TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT INTO llm_settings (id, provider_name, minimax_api_key, minimax_model, "
        "minimax_base_url, updated_at) VALUES (1, 'minimax', 'mm-secreta', 'MiniMax-M1', "
        "'https://api.minimax.io/v1', '2026-08-27T00:00:00')"
    )
    conn.commit()

    settings._migrate_generic_columns(conn)

    loaded = settings.load_llm_config(conn)
    assert loaded.provider_name == "minimax"
    assert loaded.api_key == "mm-secreta"
    assert loaded.model == "MiniMax-M1"
    assert loaded.base_url == "https://api.minimax.io/v1"


def test_migrate_generic_columns_is_a_no_op_on_an_already_generic_table():
    conn = _conn()
    settings.save_llm_config(
        conn, "gemini", "g-secreta", "gemini-3.1-flash-lite", None, "2026-09-11T00:00:00"
    )

    settings._migrate_generic_columns(conn)

    loaded = settings.load_llm_config(conn)
    assert loaded.api_key == "g-secreta"
    assert loaded.model == "gemini-3.1-flash-lite"
