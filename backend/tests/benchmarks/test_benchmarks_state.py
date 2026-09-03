import sqlite3
import time
from pathlib import Path

import pytest

from app.benchmarks import pipeline, state
from app.extraction import store
from app.schemas import BenchmarkDirectionSummary, BenchmarkRunStatus, BenchmarkRunSummary


@pytest.fixture(autouse=True)
def isolated_sync_status_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    # Archivo en disco (no ":memory:") a proposito -- mismo motivo que
    # tests/extraction/test_state.py: state.py cierra la conexion despues de cada
    # persist/hydrate, igual que hace el resto del proyecto contra Turso.
    db_path = tmp_path / "sync_status.db"
    init_conn = sqlite3.connect(db_path, check_same_thread=False)
    store._init_schema(init_conn)
    init_conn.close()
    monkeypatch.setattr(
        store, "get_connection", lambda: sqlite3.connect(db_path, check_same_thread=False)
    )
    state._hydrated = False
    yield
    state._hydrated = False


@pytest.fixture(autouse=True)
def reset_status():
    state._status = BenchmarkRunStatus()
    yield
    state._status = BenchmarkRunStatus()


def _fake_run(ok: bool = True) -> BenchmarkRunSummary:
    return BenchmarkRunSummary(
        started_at="2026-08-18T00:00:00-05:00",
        finished_at="2026-08-18T00:05:00-05:00",
        ok=ok,
        directions=[
            BenchmarkDirectionSummary(
                direction="attention", action="analyzed" if ok else "failed"
            )
        ],
    )


def _wait_until_not_running(timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while state._status.phase == "running":
        assert time.monotonic() < deadline, "el benchmark en background nunca termino"
        time.sleep(0.01)


def test_start_benchmark_run_sets_phase_running_immediately(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pipeline, "run_benchmark_cycle", lambda directions, **kwargs: _fake_run(ok=True))

    status = state.start_benchmark_run()

    assert status.phase == "running"
    assert status.started_at is not None
    _wait_until_not_running()


def test_start_benchmark_run_eventually_reaches_done_with_the_summary(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(pipeline, "run_benchmark_cycle", lambda directions, **kwargs: _fake_run(ok=True))

    state.start_benchmark_run()
    _wait_until_not_running()

    status = state.benchmark_run_status()
    assert status.phase == "done"
    assert status.result is not None
    assert status.result.ok is True
    assert not state._lock.locked()


def test_start_benchmark_run_passes_through_the_requested_directions(
    monkeypatch: pytest.MonkeyPatch,
):
    seen = []
    monkeypatch.setattr(
        pipeline,
        "run_benchmark_cycle",
        lambda directions, **kwargs: (seen.append(directions), _fake_run(ok=True))[1],
    )

    state.start_benchmark_run(["attention"])
    _wait_until_not_running()

    assert seen == [["attention"]]


def test_start_benchmark_run_reaches_error_phase_if_pipeline_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    def boom(directions, **kwargs):
        raise RuntimeError("login failed")

    monkeypatch.setattr(pipeline, "run_benchmark_cycle", boom)

    state.start_benchmark_run()
    _wait_until_not_running()

    status = state.benchmark_run_status()
    assert status.phase == "error"
    assert status.error == "login failed"
    assert not state._lock.locked()


def test_start_benchmark_run_raises_already_running_if_lock_held(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(pipeline, "run_benchmark_cycle", lambda directions, **kwargs: _fake_run(ok=True))
    state._lock.acquire()
    try:
        with pytest.raises(state.AlreadyRunningError):
            state.start_benchmark_run()
    finally:
        state._lock.release()


def test_benchmark_run_status_defaults_to_idle():
    assert state.benchmark_run_status().phase == "idle"


def test_benchmark_run_status_hydrates_from_the_store_after_a_simulated_restart(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(pipeline, "run_benchmark_cycle", lambda directions, **kwargs: _fake_run(ok=True))
    state.start_benchmark_run()
    _wait_until_not_running()

    state._status = BenchmarkRunStatus()
    state._hydrated = False

    hydrated = state.benchmark_run_status()

    assert hydrated.phase == "done"
    assert hydrated.result is not None
    assert hydrated.result.ok is True


def _simulate_a_run_interrupted_by_a_restart(conn) -> int:
    """El proceso murio a mitad de una corrida -- create_benchmark_run() paso, pero
    finish_benchmark_run() nunca corrio, y el sync_status persistido se quedo en
    phase="running" (nunca se volvio a llamar _persist_status con "done"/"error")."""
    run_id = store.create_benchmark_run(
        conn, "2026-08-27T00:00:00-05:00", None, None, False, ["attention"]
    )
    running_status = BenchmarkRunStatus(phase="running", started_at="2026-08-27T00:00:00-05:00")
    store.save_sync_status(
        conn, state._KIND_BENCHMARK_RUN_STATUS, running_status.model_dump(mode="json"),
        "2026-08-27T00:00:00-05:00",
    )
    return run_id


def test_reconcile_startup_state_marks_the_orphaned_run_row_as_failed():
    conn = store.get_connection()
    run_id = _simulate_a_run_interrupted_by_a_restart(conn)
    conn.close()

    state.reconcile_startup_state()

    conn = store.get_connection()
    runs = {r["id"]: r for r in store.list_benchmark_runs(conn)}
    assert runs[run_id]["finished_at"] is not None
    assert runs[run_id]["ok"] is False
    assert "reinici" in runs[run_id]["error"].lower()


def test_reconcile_startup_state_fixes_the_persisted_running_status():
    conn = store.get_connection()
    _simulate_a_run_interrupted_by_a_restart(conn)
    conn.close()

    state.reconcile_startup_state()

    assert state._status.phase == "error"
    assert state._status.error is not None and "reinici" in state._status.error.lower()
    # No debe volver a hidratar el "running" viejo desde la DB despues de esto.
    assert state._hydrated is True
    assert state.benchmark_run_status().phase == "error"


def test_reconcile_startup_state_is_a_noop_when_nothing_is_orphaned():
    conn = store.get_connection()
    run_id = store.create_benchmark_run(
        conn, "2026-08-27T00:00:00-05:00", None, None, False, ["attention"]
    )
    store.finish_benchmark_run(conn, run_id, "2026-08-27T00:05:00-05:00", True, "[]")
    conn.close()

    state.reconcile_startup_state()

    assert state._status.phase == "idle"
    conn = store.get_connection()
    runs = {r["id"]: r for r in store.list_benchmark_runs(conn)}
    assert runs[run_id]["ok"] is True
    assert runs[run_id]["error"] is None
