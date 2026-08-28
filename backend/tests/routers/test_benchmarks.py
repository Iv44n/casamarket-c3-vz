import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.auth import store as auth_store
from app.auth.dependencies import CurrentUser, get_current_user, require_admin
from app.benchmarks import settings as llm_settings
from app.benchmarks import state
from app.extraction import store
from app.main import app
from app.schemas import BenchmarkDirectionSummary, BenchmarkRunStatus, BenchmarkRunSummary

_RUNNING = BenchmarkRunStatus(phase="running", started_at="2026-08-18T00:00:00-05:00")

_DONE = BenchmarkRunStatus(
    phase="done",
    started_at="2026-08-18T00:00:00-05:00",
    finished_at="2026-08-18T00:05:00-05:00",
    result=BenchmarkRunSummary(
        started_at="2026-08-18T00:00:00-05:00",
        finished_at="2026-08-18T00:05:00-05:00",
        ok=True,
        directions=[BenchmarkDirectionSummary(direction="attention", action="analyzed")],
    ),
)


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(1, "test", True)
    app.dependency_overrides[require_admin] = lambda: CurrentUser(1, "test", True)
    # main.py's lifespan hook toca auth_store.get_connection() (bootstrap admin) en cada
    # arranque -- sin esto, "with TestClient(app)" pega contra la Turso real en cada test.
    # Los tests que necesitan probar el 403 real de require_admin (sin el override de arriba)
    # remonkeypatchean esto ellos mismos con su propio archivo/conexion.
    auth_db_path = tmp_path / "auth-lifespan.db"

    def _fake_auth_connection() -> sqlite3.Connection:
        conn = sqlite3.connect(str(auth_db_path), check_same_thread=False)
        auth_store._init_schema(conn)
        return conn

    monkeypatch.setattr(auth_store, "get_connection", _fake_auth_connection)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_run_benchmarks_returns_202_and_the_running_status(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(state, "start_benchmark_run", lambda directions=None, **kwargs: _RUNNING)

    response = client.post("/benchmarks/run")

    assert response.status_code == 202
    assert response.json() == _RUNNING.model_dump()


def test_run_benchmarks_passes_through_the_requested_directions(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    seen = []
    monkeypatch.setattr(
        state,
        "start_benchmark_run",
        lambda directions=None, **kwargs: (seen.append(directions), _RUNNING)[1],
    )

    response = client.post("/benchmarks/run", json={"directions": ["attention"]})

    assert response.status_code == 202
    assert seen == [["attention"]]


def test_run_benchmarks_accepts_date_range_and_force_reanalyze(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    seen = {}

    def fake_start(directions=None, **kwargs):
        seen.update(kwargs)
        seen["directions"] = directions
        return _RUNNING

    monkeypatch.setattr(state, "start_benchmark_run", fake_start)

    response = client.post(
        "/benchmarks/run",
        json={
            "directions": ["attention"],
            "date_from": "2026-08-20",
            "date_to": "2026-08-20",
            "force_reanalyze": True,
        },
    )

    assert response.status_code == 202
    assert seen == {
        "directions": ["attention"],
        "date_from": "2026-08-20",
        "date_to": "2026-08-20",
        "force_reanalyze": True,
    }


def test_run_benchmarks_rejects_an_unknown_direction(client: TestClient):
    response = client.post("/benchmarks/run", json={"directions": ["sideways"]})

    assert response.status_code == 422


def test_run_benchmarks_returns_409_when_already_running(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    def boom(directions=None, **kwargs):
        raise state.AlreadyRunningError("ya hay una corrida de benchmarks en curso")

    monkeypatch.setattr(state, "start_benchmark_run", boom)

    response = client.post("/benchmarks/run")

    assert response.status_code == 409


def test_run_status_returns_idle_before_any_run(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(state, "benchmark_run_status", lambda: BenchmarkRunStatus())

    response = client.get("/benchmarks/run/status")

    assert response.json() == BenchmarkRunStatus().model_dump()


def test_run_status_returns_the_done_status(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    monkeypatch.setattr(state, "benchmark_run_status", lambda: _DONE)

    response = client.get("/benchmarks/run/status")

    assert response.json() == _DONE.model_dump()


def test_results_returns_rows_from_the_store(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    store._init_schema(conn)
    store.record_benchmark_results(
        conn,
        [
            {
                "id_atencion": "1",
                "direction": "attention",
                "agente": "Ana",
                "campana": "Soporte",
                "estado": "Cerrada",
                "first_response_seconds": 90.0,
                "has_greeting": True,
                "has_farewell": True,
                "row_json": {},
            }
        ],
        "2026-08-18T00:00:00",
    )
    monkeypatch.setattr(store, "get_connection", lambda: conn)

    response = client.get("/benchmarks/results")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id_atencion"] == "1"
    assert body[0]["quality_ok"] is True


def test_results_filters_by_direction(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    store._init_schema(conn)
    store.record_benchmark_results(
        conn,
        [
            {"id_atencion": "in_dir", "direction": "attention", "row_json": {}},
            {"id_atencion": "other_dir", "direction": "outboundattention", "row_json": {}},
        ],
        "2026-08-18T00:00:00",
    )
    monkeypatch.setattr(store, "get_connection", lambda: conn)

    response = client.get("/benchmarks/results", params={"direction": "attention"})

    assert [row["id_atencion"] for row in response.json()] == ["in_dir"]


def test_results_422s_for_a_malformed_date(client: TestClient):
    response = client.get("/benchmarks/results", params={"date_from": "18-08-2026"})

    assert response.status_code == 422


def test_list_runs_returns_run_history(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    store._init_schema(conn)
    run_id = store.create_benchmark_run(
        conn, "2026-08-27T00:00:00", "2026-08-27", "2026-08-27", False, ["attention"]
    )
    store.finish_benchmark_run(
        conn,
        run_id,
        "2026-08-27T00:05:00",
        True,
        '[{"direction": "attention", "action": "analyzed", "cases_closed": 1, '
        '"cases_pending": 0, "cases_with_pdf": 1, "cases_analyzed": 1, "error": null}]',
    )
    monkeypatch.setattr(store, "get_connection", lambda: conn)

    response = client.get("/benchmarks/runs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == run_id
    assert body[0]["ok"] is True
    assert body[0]["date_from"] == "2026-08-27"
    assert body[0]["requested_directions"] == ["attention"]
    assert body[0]["directions"][0]["direction"] == "attention"


def _patch_llm_settings_connection(monkeypatch: pytest.MonkeyPatch, tmp_path):
    # Conexion fresca por llamada, respaldada por un archivo temporal -- mismo motivo que
    # tests/routers/test_auth.py: un lifespan/otro llamador no debe dejar la conexion
    # inutilizable para el resto del test si comparten una sola conexion en vez de una por call.
    db_path = tmp_path / "llm-settings-test.db"

    def _get_connection() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        llm_settings._init_schema(conn)
        return conn

    monkeypatch.setattr(llm_settings, "get_connection", _get_connection)


def test_get_llm_settings_without_admin_returns_403(
    client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    # Saca el override de require_admin (el fixture `client` lo pone por default para las
    # otras pruebas de este archivo) para que corra la verificacion real contra la DB de auth
    # -- con una tabla users vacia, "test" no existe -> 403. Mismo store.get_connection que
    # tests/routers/test_auth.py monkeypatchea, para no pegarle a la Turso real desde un test.
    del app.dependency_overrides[require_admin]

    db_path = tmp_path / "auth-test.db"

    def _get_auth_connection() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        auth_store._init_schema(conn)
        return conn

    monkeypatch.setattr(auth_store, "get_connection", _get_auth_connection)

    response = client.get("/benchmarks/settings")

    assert response.status_code == 403


def test_get_llm_settings_defaults_when_nothing_configured_yet(
    client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    _patch_llm_settings_connection(monkeypatch, tmp_path)

    response = client.get("/benchmarks/settings")

    assert response.status_code == 200
    assert response.json() == {
        "provider_name": "minimax",
        "minimax_model": None,
        "minimax_base_url": None,
        "has_api_key": False,
        "updated_at": None,
    }


def test_put_llm_settings_saves_and_never_returns_the_raw_api_key(
    client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    _patch_llm_settings_connection(monkeypatch, tmp_path)

    response = client.put(
        "/benchmarks/settings",
        json={
            "minimax_api_key": "mm-secreta",
            "minimax_model": "MiniMax-M1",
            "minimax_base_url": "https://api.minimax.io/v1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_api_key"] is True
    assert body["minimax_model"] == "MiniMax-M1"
    assert "minimax_api_key" not in body
    assert "mm-secreta" not in response.text


def test_put_llm_settings_without_api_key_preserves_the_existing_one(
    client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    _patch_llm_settings_connection(monkeypatch, tmp_path)
    client.put(
        "/benchmarks/settings",
        json={
            "minimax_api_key": "mm-secreta",
            "minimax_model": "MiniMax-M1",
            "minimax_base_url": "https://api.minimax.io/v1",
        },
    )

    response = client.put(
        "/benchmarks/settings",
        json={"minimax_model": "MiniMax-M2", "minimax_base_url": "https://api.minimax.io/v1"},
    )

    assert response.status_code == 200
    assert response.json()["has_api_key"] is True
    assert response.json()["minimax_model"] == "MiniMax-M2"
