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
# y su propia fila en benchmark_run, asi que correr ambos en paralelo es seguro.
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


def _run_worker(
    started_at: str,
    directions: list[str] | None,
    date_from: str | None,
    date_to: str | None,
    force_reanalyze: bool,
) -> None:
    global _status
    logger.info("Benchmarks: corriendo en background (%s)", directions or "todas")
    try:
        run = pipeline.run_benchmark_cycle(
            directions, date_from=date_from, date_to=date_to, force_reanalyze=force_reanalyze
        )
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


def start_benchmark_run(
    directions: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    force_reanalyze: bool = False,
) -> BenchmarkRunStatus:
    global _status
    if not _lock.acquire(blocking=False):
        raise AlreadyRunningError("Ya hay una corrida de benchmarks en curso.")

    started_at = datetime.now(config.TZ).isoformat()
    running_status = BenchmarkRunStatus(phase="running", started_at=started_at)
    _status = running_status
    _persist_status(running_status)
    threading.Thread(
        target=_run_worker,
        args=(started_at, directions, date_from, date_to, force_reanalyze),
        daemon=True,
    ).start()
    return running_status


def reconcile_startup_state() -> None:
    """Se llama una sola vez al arrancar el proceso (main.py's lifespan), ANTES de aceptar
    requests -- si el proceso anterior murio a mitad de una corrida de benchmarks (Render free
    tier reiniciando el dyno durante una corrida que puede tardar horas, por ejemplo),
    _run_worker() nunca llego a su except/finally: ni la fila de benchmark_run
    (finished_at NULL) ni el sync_status persistido (phase="running") se actualizan solos, y
    quedan mintiendo para siempre -- el proceso nuevo tiene su propio _lock libre, asi que
    ademas GET /benchmarks/run/status terminaria re-hidratando ese "running" viejo la primera
    vez que alguien lo consulte (ver benchmark_run_status() mas abajo), aunque no haya nada
    corriendo de verdad. Esto marca ambos como fallidos con un error claro en vez de dejarlos
    "corriendo" indefinidamente -- no reintenta la corrida sola, un admin la vuelve a disparar
    a mano si hace falta."""
    global _status, _hydrated
    now = datetime.now(config.TZ).isoformat()
    error_message = "Interrumpido: el servidor se reinicio antes de que la corrida terminara."

    try:
        conn = store.get_connection()
        try:
            reconciled_ids = store.reconcile_orphaned_benchmark_runs(conn, now, error_message)
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("No se pudieron reconciliar corridas de benchmarks huerfanas -- %s", exc)
        reconciled_ids = []
    if reconciled_ids:
        logger.warning(
            "Benchmarks: %d corrida(s) quedaron interrumpidas por un reinicio anterior (ids %s)",
            len(reconciled_ids),
            reconciled_ids,
        )

    try:
        conn = store.get_connection()
        try:
            data = store.load_sync_status(conn, _KIND_BENCHMARK_RUN_STATUS)
        finally:
            conn.close()
        persisted = BenchmarkRunStatus.model_validate(data) if data is not None else None
        if persisted is not None and persisted.phase == "running":
            error_status = BenchmarkRunStatus(
                phase="error",
                started_at=persisted.started_at,
                finished_at=now,
                error=error_message,
            )
            _persist_status(error_status)
            _status = error_status
    except Exception as exc:
        logger.warning("No se pudo reconciliar el estado de benchmarks persistido -- %s", exc)
    _hydrated = True


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
