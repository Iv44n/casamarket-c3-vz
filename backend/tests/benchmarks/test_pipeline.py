import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from app import config, schemas
from app.benchmarks import pipeline
from app.c3 import downloads, massive
from app.extraction import store
from tests.conftest import minimal_pdf_bytes


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    store._init_schema(conn)
    return conn


def _closed_row(id_atencion: str, first_response: str = "00:01:30") -> dict:
    return {
        "ID atención": id_atencion,
        "Estado": "Cerrada",
        "Agente": "Ana",
        "Campaña": "Soporte",
        "Fecha registro": "01/08/2026",
        "Hora registro": "08:00:00",
        "Fecha final": "18/08/2026",
        "Hora final": "09:00:00",
        "Tiempo de primera respuesta": first_response,
    }


class _FakeProvider:
    def __init__(self):
        self.calls: list[str] = []

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        return (
            '{"greeting_level": "formal", "has_farewell": true, "complexity": "baja", '
            '"handled_well_for_complexity": true, "spelling_ok": true, "notes": "ok"}'
        )


def _fake_zip_download_result(zip_path: Path) -> downloads.DownloadResult:
    return downloads.DownloadResult(
        job=downloads.DownloadJob(name="attention_masivo", endpoint="/x", params={}),
        status_code=200,
        path=zip_path,
        content_type="application/zip",
        size_bytes=zip_path.stat().st_size,
        elapsed_seconds=0.1,
    )


@pytest.mark.parametrize(
    "value, expected",
    [
        ("00:01:30", 90.0),
        ("01:00:00", 3600.0),
        ("-", None),
        ("", None),
        ("N.A", None),
        ("n.a", None),
        (None, None),
        ("1:30", None),
        ("bad:input:here", None),
    ],
)
def test_parse_hhmmss_seconds(value, expected):
    assert pipeline._parse_hhmmss_seconds(value) == expected


def test_build_case_benchmarks_maps_fields_and_handles_missing_pdf():
    rows = {
        "1": {
            "Agente": "Ana",
            "Campaña": "Soporte",
            "Estado": "Cerrada",
            "Tiempo de primera respuesta": "00:00:30",
        },
        "2": {
            "Agente": "Luis",
            "Campaña": "Ventas",
            "Estado": "Cerrada",
            "Tiempo de primera respuesta": "-",
        },
    }
    zip_texts = {"1": "hola"}

    cases = pipeline.build_case_benchmarks(rows, zip_texts, "attention")
    by_id = {c.id_atencion: c for c in cases}

    assert by_id["1"].conversation_text == "hola"
    assert by_id["1"].first_response_seconds == 30.0
    assert by_id["2"].conversation_text is None
    assert by_id["2"].first_response_seconds is None


def test_build_case_benchmarks_marks_had_transfer_from_transfer_origins():
    rows = {
        "1": {"Agente": "Ana", "Campaña": "Soporte", "Estado": "Cerrada"},
        "2": {"Agente": "Luis", "Campaña": "Ventas", "Estado": "Cerrada"},
    }

    cases = pipeline.build_case_benchmarks(
        rows, {}, "attention", transfer_origins={"1": ["Carla"]}
    )
    by_id = {c.id_atencion: c for c in cases}

    assert by_id["1"].had_transfer is True
    assert by_id["1"].transferred_from_agents == ["Carla"]
    assert by_id["2"].had_transfer is False
    assert by_id["2"].transferred_from_agents == []


def test_build_case_benchmarks_defaults_had_transfer_to_false_without_transfer_origins():
    rows = {"1": {"Agente": "Ana", "Campaña": "Soporte", "Estado": "Cerrada"}}

    cases = pipeline.build_case_benchmarks(rows, {}, "attention")

    assert cases[0].had_transfer is False
    assert cases[0].transferred_from_agents == []


def test_analyze_direction_records_response_time_for_all_pending_and_judges_only_those_with_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    conn = _conn()
    store.upsert_report_rows(
        conn, "attention", [_closed_row("1"), _closed_row("2")], "2026-08-18T00:00:00"
    )

    zip_path = tmp_path / "attention_masivo.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("attention_1.pdf", minimal_pdf_bytes("Hola, buen dia"))

    fake_result = _fake_zip_download_result(zip_path)
    monkeypatch.setattr(
        pipeline.massive, "run_direction", lambda client, direction, **kwargs: fake_result
    )
    provider = _FakeProvider()

    summary = pipeline.analyze_direction(
        object(),
        provider,
        conn,
        "attention",
        concurrency=2,
        lookback_days=3650,
        sleep=lambda s: None,
    )

    assert summary.action == "analyzed"
    assert summary.cases_closed == 2
    assert summary.cases_pending == 2
    assert summary.cases_with_pdf == 1
    assert summary.cases_analyzed == 1
    assert len(provider.calls) == 1

    rows = {r["id_atencion"]: r for r in store.benchmark_result_rows(conn)}
    assert rows["1"]["greeting_level"] == "formal"
    assert rows["1"]["quality_ok"] is True
    assert rows["1"]["first_response_seconds"] == 90.0
    assert rows["2"]["greeting_level"] is None
    assert rows["2"]["first_response_seconds"] == 90.0


def test_analyze_direction_asks_about_transfer_only_for_cases_with_a_transfer_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    conn = _conn()
    store.upsert_report_rows(
        conn,
        "attention",
        [_closed_row("has_transfer"), _closed_row("no_transfer")],
        "2026-08-18T00:00:00",
    )
    store.upsert_report_rows(
        conn,
        "transfer",
        [
            {
                "Atención ID": "has_transfer",
                "Fecha": "2026-08-18",
                "Hora": "10:00:00",
                "Agente Origen": "Ana",
                "Destino": "Luis",
            }
        ],
        "2026-08-18T00:00:00",
    )

    zip_path = tmp_path / "attention_masivo.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "attention_has_transfer.pdf", minimal_pdf_bytes("Te transfiero, un momento")
        )
        zf.writestr("attention_no_transfer.pdf", minimal_pdf_bytes("Hola, buen dia"))
    fake_result = _fake_zip_download_result(zip_path)
    monkeypatch.setattr(
        pipeline.massive, "run_direction", lambda client, direction, **kwargs: fake_result
    )

    class _TransferAwareProvider:
        def __init__(self):
            self.prompts: list[str] = []

        def complete(self, prompt: str) -> str:
            self.prompts.append(prompt)
            data = {
                "greeting_level": "formal",
                "has_farewell": True,
                "complexity": "baja",
                "handled_well_for_complexity": True,
                "spelling_ok": True,
                "notes": "ok",
            }
            # El prompt solo incluye la clave "informed_transfer" en su forma JSON pedida
            # cuando judge_conversation recibio una lista no vacia de transferred_from_agents --
            # confirma que se llamo con el valor correcto por caso sin depender de mockear
            # judge_conversation.
            if "informed_transfer" in prompt:
                data["informed_transfer"] = True
            return json.dumps(data)

    provider = _TransferAwareProvider()

    pipeline.analyze_direction(
        object(),
        provider,
        conn,
        "attention",
        concurrency=2,
        lookback_days=3650,
        sleep=lambda s: None,
    )

    assert len(provider.prompts) == 2
    asked_transfer = {"informed_transfer" in p for p in provider.prompts}
    assert asked_transfer == {True, False}

    rows = {r["id_atencion"]: r for r in store.benchmark_result_rows(conn)}
    assert rows["has_transfer"]["had_transfer"] is True
    assert rows["has_transfer"]["transferred_from_agents"] == ["Ana"]
    assert rows["has_transfer"]["informed_transfer"] is True
    assert rows["has_transfer"]["quality_ok"] is True
    assert rows["no_transfer"]["had_transfer"] is False
    assert rows["no_transfer"]["transferred_from_agents"] == []
    assert rows["no_transfer"]["informed_transfer"] is None
    assert rows["no_transfer"]["quality_ok"] is True


def test_analyze_direction_passes_the_case_campana_to_judge_conversation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    conn = _conn()
    store.upsert_report_rows(
        conn,
        "attention",
        [{**_closed_row("1"), "Campaña": "Activaciones"}, _closed_row("2")],
        "2026-08-18T00:00:00",
    )
    zip_path = tmp_path / "attention_masivo.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("attention_1.pdf", minimal_pdf_bytes("Hola, te contacto de Casa Market"))
        zf.writestr("attention_2.pdf", minimal_pdf_bytes("Hola, buen dia"))
    fake_result = _fake_zip_download_result(zip_path)
    monkeypatch.setattr(
        pipeline.massive, "run_direction", lambda client, direction, **kwargs: fake_result
    )
    provider = _FakeProvider()

    pipeline.analyze_direction(
        object(), provider, conn, "attention", concurrency=2, lookback_days=3650,
        sleep=lambda s: None,
    )

    activaciones_prompts = [p for p in provider.calls if "Hola, te contacto" in p]
    soporte_prompts = [p for p in provider.calls if "Hola, buen dia" in p]
    assert len(activaciones_prompts) == 1
    assert len(soporte_prompts) == 1
    assert "Activaciones" in activaciones_prompts[0]
    assert "Activaciones" not in soporte_prompts[0]


def test_analyze_direction_does_not_re_spend_llm_on_already_judged_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    conn = _conn()
    store.upsert_report_rows(conn, "attention", [_closed_row("1")], "2026-08-18T00:00:00")
    zip_path = tmp_path / "attention_masivo.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("attention_1.pdf", minimal_pdf_bytes("Hola. Chau"))
    fake_result = _fake_zip_download_result(zip_path)
    monkeypatch.setattr(
        pipeline.massive, "run_direction", lambda client, direction, **kwargs: fake_result
    )
    provider = _FakeProvider()

    kwargs = {"lookback_days": 3650, "sleep": lambda s: None}
    pipeline.analyze_direction(object(), provider, conn, "attention", **kwargs)
    pipeline.analyze_direction(object(), provider, conn, "attention", **kwargs)

    assert len(provider.calls) == 1


def test_analyze_direction_force_reanalyze_re_judges_already_benchmarked_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    conn = _conn()
    store.upsert_report_rows(conn, "attention", [_closed_row("1")], "2026-08-18T00:00:00")
    zip_path = tmp_path / "attention_masivo.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("attention_1.pdf", minimal_pdf_bytes("Hola. Chau"))
    fake_result = _fake_zip_download_result(zip_path)
    monkeypatch.setattr(
        pipeline.massive, "run_direction", lambda client, direction, **kwargs: fake_result
    )
    provider = _FakeProvider()
    kwargs = {"lookback_days": 3650, "sleep": lambda s: None}

    pipeline.analyze_direction(object(), provider, conn, "attention", **kwargs)
    assert len(provider.calls) == 1

    pipeline.analyze_direction(
        object(), provider, conn, "attention", force_reanalyze=True, **kwargs
    )

    assert len(provider.calls) == 2  # se volvio a juzgar aunque ya tenia veredicto
    rows = conn.execute(
        "SELECT COUNT(*) FROM benchmark_result WHERE id_atencion = '1'"
    ).fetchone()[0]
    assert rows == 2  # las dos corridas quedan, no se piso la primera


def test_analyze_direction_force_reanalyze_does_not_overwrite_a_real_verdict_with_a_blank_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Un caso ya tiene un veredicto real de una corrida anterior. Esta corrida (force_reanalyze)
    # no encuentra su PDF en el zip -- no debe agregar una fila en blanco que "gane" por ser la
    # mas reciente y esconda el veredicto bueno (ver benchmark_result_rows -- MAX(id)).
    conn = _conn()
    store.upsert_report_rows(conn, "attention", [_closed_row("1")], "2026-08-18T00:00:00")
    store.record_benchmark_results(
        conn,
        [
            {
                "id_atencion": "1",
                "direction": "attention",
                "greeting_level": "formal",
                "has_farewell": True,
                "row_json": {},
            }
        ],
        "2026-08-18T00:00:00",
        run_id=1,
    )

    empty_zip_path = tmp_path / "attention_masivo_empty.zip"
    with zipfile.ZipFile(empty_zip_path, "w"):
        pass  # zip sin PDFs -- el caso no aparece en zip_texts esta vez
    fake_result = _fake_zip_download_result(empty_zip_path)
    monkeypatch.setattr(
        pipeline.massive, "run_direction", lambda client, direction, **kwargs: fake_result
    )

    pipeline.analyze_direction(
        object(),
        _FakeProvider(),
        conn,
        "attention",
        force_reanalyze=True,
        lookback_days=3650,
        sleep=lambda s: None,
    )

    rows = store.benchmark_result_rows(conn)
    assert len(rows) == 1
    assert rows[0]["greeting_level"] == "formal"  # el veredicto bueno sigue siendo el que se muestra


def test_analyze_direction_uses_the_given_date_range_instead_of_the_default_lookback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    conn = _conn()
    store.upsert_report_rows(
        conn,
        "attention",
        [
            {**_closed_row("old"), "Fecha final": "01/01/2026"},
            {**_closed_row("in_range"), "Fecha final": "18/08/2026"},
        ],
        "2026-08-18T00:00:00",
    )
    empty_zip_path = tmp_path / "attention_masivo_empty.zip"
    with zipfile.ZipFile(empty_zip_path, "w"):
        pass
    fake_result = _fake_zip_download_result(empty_zip_path)
    monkeypatch.setattr(
        pipeline.massive, "run_direction", lambda client, direction, **kwargs: fake_result
    )

    summary = pipeline.analyze_direction(
        object(),
        _FakeProvider(),
        conn,
        "attention",
        date_from="2026-08-15",
        date_to="2026-08-20",
        sleep=lambda s: None,
    )

    assert summary.cases_closed == 1  # solo "in_range" cae en el rango pedido


def test_analyze_direction_returns_failed_summary_when_massive_run_raises(
    monkeypatch: pytest.MonkeyPatch
):
    conn = _conn()

    def boom(client, direction, **kwargs):
        raise massive.MassiveError("c3 esta caido")

    monkeypatch.setattr(pipeline.massive, "run_direction", boom)

    summary = pipeline.analyze_direction(object(), _FakeProvider(), conn, "attention")

    assert summary.action == "failed"
    assert "c3 esta caido" in summary.error


class _FakeC3Client:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _fake_summary(direction: str, action: str = "analyzed") -> schemas.BenchmarkDirectionSummary:
    return schemas.BenchmarkDirectionSummary(direction=direction, action=action)


def test_run_benchmark_cycle_logs_in_once_and_runs_each_direction_in_order(
    monkeypatch: pytest.MonkeyPatch
):
    fake_client = _FakeC3Client()
    monkeypatch.setattr(pipeline.massive.session, "login", lambda creds, transport=None: fake_client)
    seen = []

    def fake_analyze(client, llm_provider, conn, direction, **kwargs):
        seen.append(direction)
        return _fake_summary(direction)

    monkeypatch.setattr(pipeline, "analyze_direction", fake_analyze)

    run = pipeline.run_benchmark_cycle(
        ["attention", "outboundattention"],
        creds=config.Credentials(base_url="https://fake.test", username="u", password="p"),
        conn=_conn(),
        llm_provider=object(),
    )

    assert seen == ["attention", "outboundattention"]
    assert fake_client.closed is True
    assert run.ok is True
    assert len(run.directions) == 2


def test_run_benchmark_cycle_defaults_to_pipeline_directions_when_none_given(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        pipeline.massive.session, "login", lambda creds, transport=None: _FakeC3Client()
    )
    seen = []
    monkeypatch.setattr(
        pipeline,
        "analyze_direction",
        lambda client, llm_provider, conn, direction, **kwargs: (
            seen.append(direction),
            _fake_summary(direction),
        )[1],
    )

    pipeline.run_benchmark_cycle(
        None,
        creds=config.Credentials(base_url="https://fake.test", username="u", password="p"),
        conn=_conn(),
        llm_provider=object(),
    )

    assert seen == list(pipeline.DIRECTIONS)


def test_run_benchmark_cycle_ok_is_false_when_a_direction_fails(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        pipeline.massive.session, "login", lambda creds, transport=None: _FakeC3Client()
    )
    monkeypatch.setattr(
        pipeline, "analyze_direction", lambda *a, **k: _fake_summary("attention", "failed")
    )

    run = pipeline.run_benchmark_cycle(
        ["attention"],
        creds=config.Credentials(base_url="https://fake.test", username="u", password="p"),
        conn=_conn(),
        llm_provider=object(),
    )

    assert run.ok is False


def test_run_benchmark_cycle_builds_llm_provider_from_settings_when_not_injected(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        pipeline.massive.session, "login", lambda creds, transport=None: _FakeC3Client()
    )
    fake_llm_config = pipeline.llm_settings.LLMConfig(
        provider_name="minimax",
        minimax_api_key="x",
        minimax_model="MiniMax-M1",
        minimax_base_url="https://api.minimax.io/v1",
    )
    settings_conn = _conn()
    monkeypatch.setattr(pipeline.llm_settings, "get_connection", lambda: settings_conn)
    monkeypatch.setattr(pipeline.llm_settings, "load_llm_config", lambda conn: fake_llm_config)
    built = {}

    def fake_build_provider(llm_config):
        built["config"] = llm_config
        return "fake-provider"

    monkeypatch.setattr(pipeline.llm_module, "build_provider", fake_build_provider)

    seen_providers = []

    def fake_analyze(client, llm_provider, conn, direction, **kwargs):
        seen_providers.append(llm_provider)
        return _fake_summary(direction)

    monkeypatch.setattr(pipeline, "analyze_direction", fake_analyze)

    pipeline.run_benchmark_cycle(
        ["attention"],
        creds=config.Credentials(base_url="https://fake.test", username="u", password="p"),
        conn=_conn(),
    )

    assert built["config"] is fake_llm_config
    assert seen_providers == ["fake-provider"]


def test_run_benchmark_cycle_raises_a_clear_error_when_llm_is_not_configured_yet(
    monkeypatch: pytest.MonkeyPatch
):
    settings_conn = _conn()
    monkeypatch.setattr(pipeline.llm_settings, "get_connection", lambda: settings_conn)
    monkeypatch.setattr(pipeline.llm_settings, "load_llm_config", lambda conn: None)

    with pytest.raises(RuntimeError, match="Configuracion"):
        pipeline.run_benchmark_cycle(
            ["attention"],
            creds=config.Credentials(base_url="https://fake.test", username="u", password="p"),
            conn=_conn(),
        )


def test_run_benchmark_cycle_persists_a_benchmark_run_row_with_the_summary(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        pipeline.massive.session, "login", lambda creds, transport=None: _FakeC3Client()
    )
    monkeypatch.setattr(
        pipeline, "analyze_direction", lambda *a, **k: _fake_summary("attention")
    )
    conn = _conn()

    pipeline.run_benchmark_cycle(
        ["attention"],
        creds=config.Credentials(base_url="https://fake.test", username="u", password="p"),
        conn=conn,
        llm_provider=object(),
        date_from="2026-08-20",
        date_to="2026-08-20",
        force_reanalyze=True,
    )

    runs = store.list_benchmark_runs(conn)
    assert len(runs) == 1
    assert runs[0]["ok"] is True
    assert runs[0]["date_from"] == "2026-08-20"
    assert runs[0]["date_to"] == "2026-08-20"
    assert runs[0]["force_reanalyze"] is True
    assert runs[0]["directions"] == ["attention"]
    assert runs[0]["result_directions"] == [{
        "direction": "attention",
        "action": "analyzed",
        "cases_closed": 0,
        "cases_pending": 0,
        "cases_with_pdf": 0,
        "cases_analyzed": 0,
        "error": None,
    }]
    assert runs[0]["finished_at"] is not None


def test_run_benchmark_cycle_persists_a_failed_benchmark_run_row_when_llm_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
):
    settings_conn = _conn()
    monkeypatch.setattr(pipeline.llm_settings, "get_connection", lambda: settings_conn)
    monkeypatch.setattr(pipeline.llm_settings, "load_llm_config", lambda conn: None)
    conn = _conn()

    with pytest.raises(RuntimeError):
        pipeline.run_benchmark_cycle(
            ["attention"],
            creds=config.Credentials(base_url="https://fake.test", username="u", password="p"),
            conn=conn,
        )

    runs = store.list_benchmark_runs(conn)
    assert len(runs) == 1
    assert runs[0]["ok"] is False
    assert "Configuracion" in runs[0]["error"]
    assert runs[0]["finished_at"] is not None
