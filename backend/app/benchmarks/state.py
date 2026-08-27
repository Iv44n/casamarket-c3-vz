import logging
import threading
from datetime import datetime

from .. import config
from ..extraction import store
from ..schemas import BenchmarkRunStatus
from . import pipeline

logger = logging.getLogger(__name__)

# Lock propio, independiente del de extraction/state.py -- una corrida de benchmarks (de
# horas) no debe bloquear el refresh regular de 5 minutos. Cada run crea su propia sesion C3
# y los upserts son idempotentes por PK, asi que correr ambos en paralelo es seguro.
_lock = threading.Lock()
_status = BenchmarkRunStatus()
_KIND_BENCHMARK_RUN_STATUS = "benchmark_run_status"
_hydrated = False


class AlreadyRunningError(RuntimeError):
    pass


def _persist_status(status: BenchmarkRunStatus) -> None:
    try:
        conn = store.get_connection()
        try:
            store.save_sync_status(
                conn,
                _KIND_BENCHMARK_RUN_STATUS,
                status.model_dump(mode="json"),
                datetime.now(config.TZ).isoformat(),
            )
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("No se pudo persistir el estado de benchmarks en la DB -- %s", exc)


def _run_worker(started_at: str, directions: list[str] | None) -> None:
    global _status
    logger.info("Benchmarks: corriendo en background (%s)", directions or "todas")
    try:
        run = pipeline.run_benchmark_cycle(directions)
    except Exception as exc:
        logger.warning("Benchmarks: fallo antes de completar -- %s", exc)
        error_status = BenchmarkRunStatus(
            phase="error",
            started_at=started_at,
            finished_at=datetime.now(config.TZ).isoformat(),
            error=str(exc),
        )
        _persist_status(error_status)
        _status = error_status
        _lock.release()
        return

    done_status = BenchmarkRunStatus(
        phase="done",
        started_at=started_at,
        finished_at=run.finished_at,
        result=run,
    )
    _persist_status(done_status)
    logger.info("Benchmarks: terminado (ok=%s)", run.ok)
    _status = done_status
    _lock.release()


def start_benchmark_run(directions: list[str] | None = None) -> BenchmarkRunStatus:
    global _status
    if not _lock.acquire(blocking=False):
        raise AlreadyRunningError("Ya hay una corrida de benchmarks en curso.")

    started_at = datetime.now(config.TZ).isoformat()
    running_status = BenchmarkRunStatus(phase="running", started_at=started_at)
    _status = running_status
    _persist_status(running_status)
    threading.Thread(
        target=_run_worker, args=(started_at, directions), daemon=True
    ).start()
    return running_status


def benchmark_run_status() -> BenchmarkRunStatus:
    global _status, _hydrated
    if _status.phase == "idle" and not _hydrated:
        _hydrated = True
        try:
            conn = store.get_connection()
            try:
                data = store.load_sync_status(conn, _KIND_BENCHMARK_RUN_STATUS)
            finally:
                conn.close()
            if data is not None:
                _status = BenchmarkRunStatus.model_validate(data)
        except Exception as exc:
            logger.warning("No se pudo leer el estado de benchmarks desde la DB -- %s", exc)
    return _status
