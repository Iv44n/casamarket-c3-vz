from pathlib import Path

import httpx
import pytest

from app import config
from app.c3 import massive, reports


@pytest.fixture(autouse=True)
def isolated_downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path / "downloads")


ATTENTION_MASSIVE = reports.EXPORT_MECHANISMS["attention"].massive_endpoint
LIST = reports.MASSIVE_LIST_ENDPOINT

FAKE_CREDS = config.Credentials(base_url="https://fake.test", username="user", password="pass")


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


def _session(client: httpx.Client) -> massive.C3Session:
    """La mayoria de los tests de este archivo no le importa la sesion en si (no la
    invalidan a proposito) -- solo envuelve el client ya armado por _sequenced_client."""
    return massive.C3Session(FAKE_CREDS, client=client)


def _json_response(data) -> httpx.Response:
    return httpx.Response(200, json=data)


def test_trigger_and_track_returns_the_new_job_id():
    sess = _session(
        _sequenced_client(
            [
                (LIST, _json_response([])),
                (ATTENTION_MASSIVE, _json_response({"success": True, "message": "ok"})),
                (LIST, _json_response([_job(1, "PENDING")])),
            ]
        )
    )

    job_id = massive.trigger_and_track(sess, "attention")

    assert job_id == 1


def test_trigger_and_track_raises_when_no_new_job_appears():
    sess = _session(
        _sequenced_client(
            [
                (LIST, _json_response([_job(1, "PENDING")])),
                (ATTENTION_MASSIVE, _json_response({"success": True, "message": "ok"})),
                (LIST, _json_response([_job(1, "PENDING")])),
            ]
        )
    )

    with pytest.raises(massive.MassiveError, match="no aparecio"):
        massive.trigger_and_track(sess, "attention")


def test_trigger_raises_when_server_reports_failure():
    sess = _session(
        _sequenced_client(
            [(ATTENTION_MASSIVE, _json_response({"success": False, "message": "sin datos"}))]
        )
    )

    with pytest.raises(massive.MassiveError):
        massive._trigger(sess, "attention")


def test_list_jobs_raises_on_non_json_response():
    sess = _session(_sequenced_client([(LIST, httpx.Response(200, text="<html>spa</html>"))]))

    with pytest.raises(massive.MassiveError, match="Accept"):
        massive._list_jobs(sess)


def test_wait_for_completion_returns_job_when_completed_immediately():
    sess = _session(
        _sequenced_client([(LIST, _json_response([_job(5, "COMPLETED", download_url="/fake/5.zip")]))])
    )

    job = massive.wait_for_completion(
        sess, "attention", 5, poll_interval_seconds=0, timeout_seconds=10, sleep=lambda s: None
    )

    assert job["status"] == "COMPLETED"
    assert job["download_url"] == "/fake/5.zip"


def test_wait_for_completion_polls_while_pending():
    sess = _session(
        _sequenced_client(
            [
                (LIST, _json_response([_job(5, "PENDING")])),
                (LIST, _json_response([_job(5, "COMPLETED", download_url="/fake/5.zip")])),
            ]
        )
    )
    sleeps = []

    job = massive.wait_for_completion(
        sess,
        "attention",
        5,
        poll_interval_seconds=1.5,
        timeout_seconds=10,
        sleep=sleeps.append,
    )

    assert job["status"] == "COMPLETED"
    assert sleeps == [1.5]


def test_wait_for_completion_retries_once_on_failure_then_succeeds():
    sess = _session(
        _sequenced_client(
            [
                (LIST, _json_response([_job(5, "FAILED", error_message="boom")])),
                (LIST, _json_response([_job(5, "FAILED", error_message="boom")])),
                (ATTENTION_MASSIVE, _json_response({"success": True, "message": "ok"})),
                (
                    LIST,
                    _json_response(
                        [_job(5, "FAILED", error_message="boom"), _job(7, "PENDING")]
                    ),
                ),
                (LIST, _json_response([_job(7, "COMPLETED", download_url="/fake/7.zip")])),
            ]
        )
    )

    job = massive.wait_for_completion(
        sess, "attention", 5, poll_interval_seconds=0, timeout_seconds=10, sleep=lambda s: None
    )

    assert job["id"] == 7
    assert job["download_url"] == "/fake/7.zip"


def test_wait_for_completion_raises_after_second_failure():
    sess = _session(
        _sequenced_client(
            [
                (LIST, _json_response([_job(5, "FAILED", error_message="boom")])),
                (LIST, _json_response([_job(5, "FAILED", error_message="boom")])),
                (ATTENTION_MASSIVE, _json_response({"success": True, "message": "ok"})),
                (
                    LIST,
                    _json_response(
                        [_job(5, "FAILED", error_message="boom"), _job(7, "PENDING")]
                    ),
                ),
                (LIST, _json_response([_job(7, "FAILED", error_message="boom otra vez")])),
            ]
        )
    )

    with pytest.raises(massive.MassiveError, match="fallo dos veces"):
        massive.wait_for_completion(
            sess,
            "attention",
            5,
            poll_interval_seconds=0,
            timeout_seconds=10,
            sleep=lambda s: None,
        )


def test_wait_for_completion_raises_on_timeout():
    sess = _session(_sequenced_client([(LIST, _json_response([_job(5, "PENDING")]))]))

    with pytest.raises(massive.MassiveError, match="no completo"):
        massive.wait_for_completion(
            sess,
            "attention",
            5,
            poll_interval_seconds=0,
            timeout_seconds=0,
            sleep=lambda s: None,
        )


def test_download_saves_the_zip_and_reports_its_size():
    body = b"contenido-del-zip"
    sess = _session(
        _sequenced_client(
            [("/fake/5.zip", httpx.Response(200, headers={"content-type": "application/zip"}, content=body))]
        )
    )

    result = massive.download(sess, "attention", "/fake/5.zip")

    assert result.size_bytes == len(body)
    assert result.path.read_bytes() == body
    assert result.path.name.startswith("attention_masivo_")


def test_run_direction_triggers_waits_and_downloads():
    body = b"contenido-del-zip"
    sess = _session(
        _sequenced_client(
            [
                (LIST, _json_response([])),
                (ATTENTION_MASSIVE, _json_response({"success": True, "message": "ok"})),
                (LIST, _json_response([_job(1, "PENDING")])),
                (LIST, _json_response([_job(1, "COMPLETED", download_url="/fake/1.zip")])),
                (
                    "/fake/1.zip",
                    httpx.Response(200, headers={"content-type": "application/zip"}, content=body),
                ),
            ]
        )
    )

    result = massive.run_direction(
        sess, "attention", poll_interval_seconds=0, timeout_seconds=10, sleep=lambda s: None
    )

    assert result.path.read_bytes() == body


def _login_and_massive_handler(steps: list[tuple[str, httpx.Response]]):
    """Handler combinado: entiende tanto el flujo de login real (GET /user/login, POST
    /user/signin, GET /user, GET del probe de is_authenticated) como los pasos de
    get_massives/trigger de `steps` -- para probar C3Session.relogin() de punta a punta,
    sin mockear session.login() por separado."""
    remaining = list(steps)
    probe_path = next(iter(config.REPORT_PATHS.values()))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == config.LOGIN_PATH and request.method == "GET":
            return httpx.Response(200, text='<input name="_token" value="tok" autocomplete="off">')
        if request.url.path == config.SIGNIN_PATH and request.method == "POST":
            return httpx.Response(302, headers={"location": "/user"})
        if request.url.path == "/user" and request.method == "GET":
            return httpx.Response(200, text="dashboard")
        if request.url.path == probe_path:
            return httpx.Response(200, text="ok")
        assert remaining, f"peticion inesperada (no quedan pasos): {request.url}"
        expected_path, response = remaining.pop(0)
        assert request.url.path == expected_path, (
            f"se esperaba {expected_path!r}, llego {request.url.path!r}"
        )
        return response

    return httpx.MockTransport(handler)


def test_list_jobs_relogins_once_on_401_and_retries():
    transport = _login_and_massive_handler(
        [
            (LIST, httpx.Response(401)),
            (LIST, _json_response([_job(1, "PENDING")])),
        ]
    )
    initial_client = httpx.Client(base_url="https://fake.test", transport=transport)
    sess = massive.C3Session(FAKE_CREDS, transport=transport, client=initial_client)

    jobs = massive._list_jobs(sess)

    assert jobs == [_job(1, "PENDING")]
    assert sess.client is not initial_client


def test_trigger_relogins_once_on_401_and_retries():
    transport = _login_and_massive_handler(
        [
            (ATTENTION_MASSIVE, httpx.Response(401)),
            (ATTENTION_MASSIVE, _json_response({"success": True, "message": "ok"})),
        ]
    )
    initial_client = httpx.Client(base_url="https://fake.test", transport=transport)
    sess = massive.C3Session(FAKE_CREDS, transport=transport, client=initial_client)

    massive._trigger(sess, "attention")  # no lanza

    assert sess.client is not initial_client


def test_get_with_relogin_propagates_a_second_401():
    transport = _login_and_massive_handler(
        [
            (LIST, httpx.Response(401)),
            (LIST, httpx.Response(401)),
        ]
    )
    initial_client = httpx.Client(base_url="https://fake.test", transport=transport)
    sess = massive.C3Session(FAKE_CREDS, transport=transport, client=initial_client)

    with pytest.raises(httpx.HTTPStatusError):
        massive._list_jobs(sess)


def test_c3_session_close_closes_the_current_client():
    client = _sequenced_client([])
    sess = massive.C3Session(FAKE_CREDS, client=client)

    sess.close()

    assert client.is_closed
