import datetime
from pathlib import Path

import httpx
import pytest

from app import config
from app.c3 import reports
from app.extraction import service


@pytest.fixture(autouse=True)
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path / "downloads")
    monkeypatch.setattr(config, "MASSIVE_STATE_FILE", tmp_path / "state" / "massive.json")


def _sequenced_client(steps: list[tuple[str, httpx.Response]]) -> httpx.Client:
    remaining = list(steps)

    def handler(request: httpx.Request) -> httpx.Response:
        assert remaining, f"peticion inesperada (no quedan pasos): {request.url}"
        expected_path, response = remaining.pop(0)
        assert request.url.path == expected_path, (
            f"se esperaba {expected_path!r}, llego {request.url.path!r}"
        )
        return response

    return httpx.Client(base_url="https://fake.test", transport=httpx.MockTransport(handler))


_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

ATTENTIONS_EXPORT = reports.EXPORT_MECHANISMS["attention"].export_endpoint
CALLS_EXPORT = reports.CALLS_EXPORT_ENDPOINT
CONTACTS_EXPORT = reports.CONTACTS_EXPORT_ENDPOINT
TRANSFER_EXPORT = reports.TRANSFER_EXPORT_ENDPOINT
ATTENTION_MASSIVE = reports.EXPORT_MECHANISMS["attention"].massive_endpoint
LIST = reports.MASSIVE_LIST_ENDPOINT


def _file_response(body: bytes = b"contenido-del-excel") -> httpx.Response:
    return httpx.Response(200, headers={"content-type": _XLSX}, content=body)


def _json_response(data) -> httpx.Response:
    return httpx.Response(200, json=data)


def _download_steps() -> list[tuple[str, httpx.Response]]:
    return [
        (ATTENTIONS_EXPORT, _file_response()),
        (ATTENTIONS_EXPORT, _file_response()),
        (CALLS_EXPORT, _file_response()),
        (CALLS_EXPORT, _file_response()),
        (CONTACTS_EXPORT, _file_response()),
        (TRANSFER_EXPORT, _file_response()),
    ]


def _backfill_steps() -> list[tuple[str, httpx.Response]]:
    return [
        (ATTENTIONS_EXPORT, _file_response()),
        (ATTENTIONS_EXPORT, _file_response()),
        (CALLS_EXPORT, _file_response()),
        (CALLS_EXPORT, _file_response()),
        (TRANSFER_EXPORT, _file_response()),
    ]


def _massive_cycle_steps() -> list[tuple[str, httpx.Response]]:
    return [
        (LIST, _json_response([])),
        (ATTENTION_MASSIVE, _json_response({"success": True, "message": "ok"})),
        (
            LIST,
            _json_response(
                [{"id": 1, "status": "PENDING", "download_url": None, "error_message": None}]
            ),
        ),
    ]


def test_run_all_downloads_everything_and_never_touches_the_massive_cycle():
    client = _sequenced_client(_download_steps())

    run = service.run_all(client)

    assert {outcome.job.name for outcome in run.jobs} == {
        "attention",
        "outboundattention",
        "callincoming",
        "calloutgoing",
        "contacts",
        "transfer",
    }
    assert all(outcome.error is None for outcome in run.jobs)
    assert run.ok is True


def test_run_all_collects_a_failed_job_without_aborting_the_rest():
    steps = _download_steps()
    steps[0] = (
        ATTENTIONS_EXPORT,
        httpx.Response(200, headers={"content-type": "text/html"}, text="<html>login</html>"),
    )
    client = _sequenced_client(steps)

    run = service.run_all(client)

    failed = next(o for o in run.jobs if o.job.name == "attention")
    assert failed.error is not None
    assert failed.result is None
    assert sum(1 for o in run.jobs if o.error is None) == 5
    assert run.ok is False


def test_run_backfill_jobs_downloads_only_the_five_dated_families():
    client = _sequenced_client(_backfill_steps())

    run = service.run_backfill_jobs(client, datetime.date(2026, 8, 10))

    assert {outcome.job.name for outcome in run.jobs} == {
        "attention",
        "outboundattention",
        "callincoming",
        "calloutgoing",
        "transfer",
    }
    assert all(outcome.job.file_date == datetime.date(2026, 8, 10) for outcome in run.jobs)
    assert all(outcome.error is None for outcome in run.jobs)
    assert run.ok is True


def test_run_massive_cycle_advances_the_massive_state_machine():
    client = _sequenced_client(_massive_cycle_steps())

    run = service.run_massive_cycle(client)

    assert run.massive is not None
    assert run.massive.action == "triggered"
    assert run.massive_error is None
    assert run.ok is True


def test_run_massive_cycle_records_a_massive_error():
    steps = _massive_cycle_steps()
    steps[0] = (LIST, httpx.Response(200, text="<html>not json</html>"))
    client = _sequenced_client(steps)

    run = service.run_massive_cycle(client)

    assert run.massive is None
    assert run.massive_error is not None
    assert run.ok is False


def _creds() -> config.Credentials:
    return config.Credentials(base_url="https://fake.test", username="user", password="pass")


def _login_steps() -> list[tuple[str, httpx.Response]]:
    probe_path = next(iter(config.REPORT_PATHS.values()))
    return [
        (config.LOGIN_PATH, httpx.Response(200, text='<input name="_token" value="tok">')),
        (config.SIGNIN_PATH, httpx.Response(302, headers={"location": "/user"})),
        ("/user", httpx.Response(200, text="dashboard")),
        (probe_path, httpx.Response(200, text="ok")),
    ]


def test_run_logs_in_then_downloads_everything_without_the_massive_cycle():
    steps = _login_steps() + _download_steps()
    remaining = list(steps)

    def handler(request: httpx.Request) -> httpx.Response:
        assert remaining, f"peticion inesperada (no quedan pasos): {request.url}"
        expected_path, response = remaining.pop(0)
        assert request.url.path == expected_path, (
            f"se esperaba {expected_path!r}, llego {request.url.path!r}"
        )
        return response

    result = service.run(_creds(), transport=httpx.MockTransport(handler))

    assert result.ok is True
    assert not remaining


def test_run_massive_logs_in_then_advances_one_step_of_the_massive_cycle():
    steps = _login_steps() + _massive_cycle_steps()
    remaining = list(steps)

    def handler(request: httpx.Request) -> httpx.Response:
        assert remaining, f"peticion inesperada (no quedan pasos): {request.url}"
        expected_path, response = remaining.pop(0)
        assert request.url.path == expected_path, (
            f"se esperaba {expected_path!r}, llego {request.url.path!r}"
        )
        return response

    result = service.run_massive(_creds(), transport=httpx.MockTransport(handler))

    assert result.ok is True


def test_run_backfill_logs_in_then_downloads_only_the_five_dated_families():
    steps = _login_steps() + _backfill_steps()
    remaining = list(steps)

    def handler(request: httpx.Request) -> httpx.Response:
        assert remaining, f"peticion inesperada (no quedan pasos): {request.url}"
        expected_path, response = remaining.pop(0)
        assert request.url.path == expected_path, (
            f"se esperaba {expected_path!r}, llego {request.url.path!r}"
        )
        return response

    result = service.run_backfill(
        datetime.date(2026, 8, 10), _creds(), transport=httpx.MockTransport(handler)
    )

    assert result.ok is True
    assert not remaining
    assert not remaining
