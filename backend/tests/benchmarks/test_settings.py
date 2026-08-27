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
    assert saved.minimax_api_key == "mm-secreta"
    assert saved.minimax_model == "MiniMax-M1"
    assert saved.minimax_base_url == "https://api.minimax.io/v1"
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
    assert loaded.minimax_api_key == "new-key"
    assert loaded.minimax_model == "MiniMax-M2"


def test_save_llm_config_with_api_key_none_preserves_the_existing_key():
    conn = _conn()
    settings.save_llm_config(
        conn, "minimax", "keep-me", "MiniMax-M1", "https://api.minimax.io/v1", "2026-08-27T00:00:00"
    )

    updated = settings.save_llm_config(
        conn, "minimax", None, "MiniMax-M2", "https://api.minimax.io/v1", "2026-08-27T00:01:00"
    )

    assert updated.minimax_api_key == "keep-me"
    assert updated.minimax_model == "MiniMax-M2"


def test_save_llm_config_with_api_key_none_and_nothing_saved_yet_leaves_it_empty():
    conn = _conn()

    saved = settings.save_llm_config(
        conn, "minimax", None, "MiniMax-M1", "https://api.minimax.io/v1", "2026-08-27T00:00:00"
    )

    assert saved.minimax_api_key is None


def test_llm_config_model_label_is_none_for_a_provider_with_no_model_field():
    llm_config = settings.LLMConfig(provider_name="unlisted")

    assert llm_config.model_label is None


def test_llm_config_model_label_returns_the_model_for_minimax():
    llm_config = settings.LLMConfig(provider_name="minimax", minimax_model="MiniMax-M1")

    assert llm_config.model_label == "MiniMax-M1"
