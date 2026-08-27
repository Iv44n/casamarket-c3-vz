import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import CurrentUser, get_current_user
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
def client():
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(1, "test", True)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_run_benchmarks_returns_202_and_the_running_status(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(state, "start_benchmark_run", lambda directions=None: _RUNNING)

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
        lambda directions=None: (seen.append(directions), _RUNNING)[1],
    )

    response = client.post("/benchmarks/run", json={"directions": ["attention"]})

    assert response.status_code == 202
    assert seen == [["attention"]]


def test_run_benchmarks_rejects_an_unknown_direction(client: TestClient):
    response = client.post("/benchmarks/run", json={"directions": ["sideways"]})

    assert response.status_code == 422


def test_run_benchmarks_returns_409_when_already_running(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    def boom(directions=None):
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
    store.upsert_benchmark_results(
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
    store.upsert_benchmark_results(
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
