import logging
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from .. import config, schemas
from ..c3 import massive, massive_zip
from ..extraction import store
from . import llm as llm_module
from . import settings as llm_settings
from .llm import LLMProvider, QualityJudgement, judge_conversation

logger = logging.getLogger(__name__)

DIRECTIONS = ("attention", "outboundattention")

_EMPTY_DURATION_VALUES = {"", "n.a", "-"}


def _parse_hhmmss_seconds(value: object) -> float | None:
    """Parsea 'Tiempo de primera respuesta' (formato 'HH:MM:SS', confirmado en vivo contra
    un xlsx real de attention). Espejo de parseDurationToSeconds en
    frontend/src/lib/duration.ts, pero restringido a 3 partes -- este campo especifico de C3
    siempre viene en ese formato (a diferencia de 'Tiempo de atencion', que mezcla HH:MM:SS
    y MM:SS)."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if trimmed.lower() in _EMPTY_DURATION_VALUES:
        return None
    parts = trimmed.split(":")
    if len(parts) != 3:
        return None
    try:
        hours, minutes, seconds = (int(p) for p in parts)
    except ValueError:
        return None
    return float(hours * 3600 + minutes * 60 + seconds)


@dataclass(frozen=True)
class CaseBenchmark:
    id_atencion: str
    direction: str
    agente: str | None
    campana: str | None
    estado: str | None
    first_response_seconds: float | None
    conversation_text: str | None
    row_json: dict


def build_case_benchmarks(
    rows: dict[str, dict], zip_texts: dict[str, str], direction: str
) -> list[CaseBenchmark]:
    """Itera `rows` (los casos PENDIENTES de veredicto -- nunca los ya benchmarkeados, ver
    store.already_benchmarked_ids) y hace `zip_texts.get(id)`; un caso cerrado sin PDF en el
    zip de hoy sigue generando un CaseBenchmark (con `conversation_text=None`), para que su
    tiempo de primera respuesta quede registrado igual aunque todavia no tenga veredicto de
    calidad."""
    cases = []
    for id_atencion, row in rows.items():
        cases.append(
            CaseBenchmark(
                id_atencion=id_atencion,
                direction=direction,
                agente=row.get("Agente"),
                campana=row.get("Campaña"),
                estado=row.get("Estado"),
                first_response_seconds=_parse_hhmmss_seconds(
                    row.get("Tiempo de primera respuesta")
                ),
                conversation_text=zip_texts.get(id_atencion) or None,
                row_json=row,
            )
        )
    return cases


def _to_benchmark_row(
    case: CaseBenchmark, judgement: QualityJudgement | None, llm_model: str | None
) -> dict:
    return {
        "id_atencion": case.id_atencion,
        "direction": case.direction,
        "agente": case.agente,
        "campana": case.campana,
        "estado": case.estado,
        "first_response_seconds": case.first_response_seconds,
        "has_greeting": judgement.has_greeting if judgement else None,
        "has_farewell": judgement.has_farewell if judgement else None,
        "llm_model": llm_model if judgement else None,
        "llm_raw": judgement.raw if judgement else None,
        "llm_notes": judgement.notes if judgement else None,
        "row_json": case.row_json,
    }


def analyze_direction(
    c3_session: massive.C3Session,
    llm_provider: LLMProvider,
    conn: store.DBConnection,
    direction: str,
    *,
    concurrency: int = config.BENCHMARK_LLM_CONCURRENCY,
    poll_interval_seconds: float = config.BENCHMARK_POLL_INTERVAL_SECONDS,
    timeout_seconds: float = config.BENCHMARK_MASSIVE_TIMEOUT_SECONDS,
    lookback_days: int = config.BENCHMARK_LOOKBACK_DAYS,
    llm_model: str | None = None,
    sleep=time.sleep,
) -> schemas.BenchmarkDirectionSummary:
    """Pipeline completo para una direccion: casos cerrados pendientes -> reporte masivo de
    C3 -> texto de los PDFs que hagan falta -> juicio del LLM (concurrente, acotado) ->
    upsert. Envuelto en try/except propio para que una direccion fallando no bloquee el
    intento de la otra (mismo espiritu que extraction.service._run_jobs)."""
    try:
        date_from = (config.hoy() - timedelta(days=lookback_days)).isoformat()
        closed = store.closed_case_rows(
            conn, direction, estados=config.BENCHMARK_CLOSED_ESTADOS, date_from=date_from
        )
        already = store.already_benchmarked_ids(conn, direction, list(closed))
        pending = {id_: row for id_, row in closed.items() if id_ not in already}

        result = massive.run_direction(
            c3_session,
            direction,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
            sleep=sleep,
        )
        zip_texts = massive_zip.extract_texts_for_ids(result.path, pending.keys())

        cases = build_case_benchmarks(pending, zip_texts, direction)

        judgements: dict[str, QualityJudgement] = {}
        judgeable = [case for case in cases if case.conversation_text]
        if judgeable:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = {
                    executor.submit(
                        judge_conversation, llm_provider, case.conversation_text
                    ): case
                    for case in judgeable
                }
                for future in as_completed(futures):
                    case = futures[future]
                    try:
                        judgements[case.id_atencion] = future.result()
                    except Exception as exc:
                        logger.warning(
                            "El LLM fallo para la atencion %s (%s) -- %s",
                            case.id_atencion,
                            direction,
                            exc,
                        )

        observed_at = datetime.now(config.TZ).isoformat()
        rows_to_store = [
            _to_benchmark_row(case, judgements.get(case.id_atencion), llm_model)
            for case in cases
        ]
        if rows_to_store:
            store.upsert_benchmark_results(conn, rows_to_store, observed_at)

        return schemas.BenchmarkDirectionSummary(
            direction=direction,
            action="analyzed",
            cases_closed=len(closed),
            cases_pending=len(pending),
            cases_with_pdf=len(zip_texts),
            cases_analyzed=len(judgements),
        )
    except Exception as exc:
        logger.warning("Benchmark de '%s' fallo -- %s", direction, exc)
        return schemas.BenchmarkDirectionSummary(
            direction=direction, action="failed", error=str(exc)
        )


def run_benchmark_cycle(
    directions: Iterable[str] | None = None,
    *,
    creds: config.Credentials | None = None,
    transport: httpx.BaseTransport | None = None,
    conn: store.DBConnection | None = None,
    llm_provider: LLMProvider | None = None,
    llm_model: str | None = None,
) -> schemas.BenchmarkRunSummary:
    """Un solo login C3 (envuelto en massive.C3Session, que se re-loguea sola si C3
    invalida la sesion -- ver su docstring), loop SECUENCIAL (no concurrente) sobre
    analyze_direction por cada direccion pedida. Si no se inyecta `llm_provider`
    (produccion), se construye desde la config guardada por un admin via
    PUT /benchmarks/settings (settings.load_llm_config()) -- el seam que los tests usan para
    pasar un LLMProvider falso es justamente inyectarlo aca."""
    resolved_directions = list(directions) if directions is not None else list(DIRECTIONS)

    if llm_provider is None:
        settings_conn = llm_settings.get_connection()
        try:
            llm_config = llm_settings.load_llm_config(settings_conn)
        finally:
            settings_conn.close()
        if llm_config is None:
            raise RuntimeError(
                "El analisis de calidad (LLM) todavia no fue configurado -- un admin tiene que "
                "completarlo en Configuracion > LLM antes de poder correr un benchmark."
            )
        llm_provider = llm_module.build_provider(llm_config)
        llm_model = llm_config.model_label

    owns_conn = conn is None
    if owns_conn:
        conn = store.get_connection()

    creds = creds or config.load_credentials()
    started_at = datetime.now(config.TZ).isoformat()
    c3_session = massive.C3Session(creds, transport=transport)
    try:
        summaries = [
            analyze_direction(c3_session, llm_provider, conn, direction, llm_model=llm_model)
            for direction in resolved_directions
        ]
    finally:
        c3_session.close()
        if owns_conn:
            conn.close()

    return schemas.BenchmarkRunSummary(
        started_at=started_at,
        finished_at=datetime.now(config.TZ).isoformat(),
        ok=all(summary.action == "analyzed" for summary in summaries),
        directions=summaries,
    )
