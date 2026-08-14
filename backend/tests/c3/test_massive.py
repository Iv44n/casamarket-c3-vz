import json
from pathlib import Path

import httpx
import pytest

from app import config
from app.c3 import massive, reports


@pytest.fixture(autouse=True)
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "MASSIVE_STATE_FILE", tmp_path / "state" / "massive.json")
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path / "downloads")


ATTENTION_MASSIVE = reports.EXPORT_MECHANISMS["attention"].massive_endpoint
LIST = reports.MASSIVE_LIST_ENDPOINT


def _job(id_, status, **extra):
    return {"id": id_, "status": status, "download_url": None, "error_message": None, **extra}


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


def _json_response(data) -> httpx.Response:
    return httpx.Response(200, json=data)


def test_first_run_with_no_state_triggers_attention():
    client = _sequenced_client(
        [
            (LIST, _json_response([])),
            (ATTENTION_MASSIVE, _json_response({"success": True, "message": "ok"})),
            (LIST, _json_response([_job(1, "PENDING")])),
        ]
    )

    result = massive.run_cycle(client)

    assert result.action == "triggered"
    assert result.name == "attention"
    assert result.job_id == 1
    saved = json.loads(config.MASSIVE_STATE_FILE.read_text())
    assert saved == {"name": "attention", "job_id": 1}


def test_waiting_when_job_still_pending():
    massive._save_state(massive._State(name="attention", job_id=5))
    client = _sequenced_client([(LIST, _json_response([_job(5, "PENDING")]))])

    result = massive.run_cycle(client)

    assert result.action == "waiting"
    assert result.name == "attention"
    assert result.status == "PENDING"
    assert json.loads(config.MASSIVE_STATE_FILE.read_text()) == {"name": "attention", "job_id": 5}


def test_completed_downloads_and_triggers_the_other_direction():
    massive._save_state(massive._State(name="attention", job_id=5))
    outbound_massive = reports.EXPORT_MECHANISMS["outboundattention"].massive_endpoint
    body = b"contenido-del-zip"

    client = _sequenced_client(
        [
            (LIST, _json_response([_job(5, "COMPLETED", download_url="/fake/download/5.zip")])),
            ("/fake/download/5.zip", httpx.Response(200, headers={"content-type": "application/zip"}, content=body)),
            (LIST, _json_response([_job(5, "COMPLETED")])),
            (outbound_massive, _json_response({"success": True, "message": "ok"})),
            (LIST, _json_response([_job(5, "COMPLETED"), _job(6, "PENDING")])),
        ]
    )

    result = massive.run_cycle(client)

    assert result.action == "downloaded"
    assert result.name == "attention"
    assert result.result.size_bytes == len(body)
    assert result.result.path.read_bytes() == body
    assert result.next_name == "outboundattention"
    assert result.next_job_id == 6
    assert json.loads(config.MASSIVE_STATE_FILE.read_text()) == {
        "name": "outboundattention",
        "job_id": 6,
    }


def test_failed_job_retries_the_same_direction():
    massive._save_state(massive._State(name="attention", job_id=5))
    client = _sequenced_client(
        [
            (LIST, _json_response([_job(5, "FAILED", error_message="boom")])),
            (LIST, _json_response([_job(5, "FAILED")])),
            (ATTENTION_MASSIVE, _json_response({"success": True, "message": "ok"})),
            (LIST, _json_response([_job(5, "FAILED"), _job(7, "PENDING")])),
        ]
    )

    result = massive.run_cycle(client)

    assert result.action == "retried"
    assert result.name == "attention"
    assert result.job_id == 7
    assert result.note == "boom"


def test_job_missing_from_listing_retries_the_same_direction():
    massive._save_state(massive._State(name="outboundattention", job_id=9))
    outbound_massive = reports.EXPORT_MECHANISMS["outboundattention"].massive_endpoint
    client = _sequenced_client(
        [
            (LIST, _json_response([])),
            (LIST, _json_response([])),
            (outbound_massive, _json_response({"success": True, "message": "ok"})),
            (LIST, _json_response([_job(10, "PENDING")])),
        ]
    )

    result = massive.run_cycle(client)

    assert result.action == "retried"
    assert result.name == "outboundattention"
    assert result.job_id == 10
    assert "ya no aparece" in result.note


def test_list_jobs_raises_on_non_json_response():
    client = _sequenced_client([(LIST, httpx.Response(200, text="<html>spa</html>"))])

    with pytest.raises(massive.MassiveError, match="Accept"):
        massive._list_jobs(client)


def test_trigger_raises_when_server_reports_failure():
    client = _sequenced_client(
        [(ATTENTION_MASSIVE, _json_response({"success": False, "message": "sin datos"}))]
    )

    with pytest.raises(massive.MassiveError):
        massive._trigger(client, "attention")


def test_trigger_and_track_raises_when_no_new_job_appears():
    client = _sequenced_client(
        [
            (LIST, _json_response([_job(1, "PENDING")])),
            (ATTENTION_MASSIVE, _json_response({"success": True, "message": "ok"})),
            (LIST, _json_response([_job(1, "PENDING")])),
        ]
    )

    with pytest.raises(massive.MassiveError, match="no aparecio"):
        massive._trigger_and_track(client, "attention")


def test_describe_covers_every_action():
    fake_result = massive.downloads.DownloadResult(
        job=massive.downloads.DownloadJob(name="attention_masivo", endpoint="/x", params={}),
        status_code=200,
        path=Path("/tmp/attention_masivo.zip"),
        content_type="application/zip",
        size_bytes=1234,
        elapsed_seconds=1.0,
    )
    cases = [
        massive.CycleResult(action="triggered", name="attention", job_id=1),
        massive.CycleResult(action="waiting", name="attention", job_id=1, status="PENDING"),
        massive.CycleResult(action="retried", name="attention", job_id=2, note="boom"),
        massive.CycleResult(
            action="downloaded",
            name="attention",
            result=fake_result,
            next_name="outboundattention",
            next_job_id=3,
        ),
    ]

    for cycle in cases:
        text = massive.describe(cycle)
        assert isinstance(text, str) and text


def test_describe_raises_on_unknown_action():
    with pytest.raises(ValueError):
        massive.describe(massive.CycleResult(action="bogus", name="attention"))
