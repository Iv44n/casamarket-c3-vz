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
        return '{"has_greeting": true, "has_farewell": true, "notes": "ok"}'


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
    assert rows["1"]["has_greeting"] is True
    assert rows["1"]["quality_ok"] is True
    assert rows["1"]["first_response_seconds"] == 90.0
    assert rows["2"]["has_greeting"] is None
    assert rows["2"]["first_response_seconds"] == 90.0


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
