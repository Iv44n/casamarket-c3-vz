import datetime
import os
import re
from pathlib import Path

import httpx
import pytest

from app import config
from app.c3 import downloads


def test_build_jobs_returns_the_five_expected_names_not_contacts():
    names = {job.name for job in downloads.build_jobs()}

    assert names == {
        "attention",
        "outboundattention",
        "callincoming",
        "calloutgoing",
        "transfer",
    }


def test_build_contacts_sync_jobs_returns_only_contacts():
    jobs = downloads.build_contacts_sync_jobs()

    assert [job.name for job in jobs] == ["contacts"]


def _job(name: str) -> downloads.DownloadJob:
    if name == "contacts":
        return downloads.build_contacts_sync_jobs()[0]
    return next(job for job in downloads.build_jobs() if job.name == name)


DATE_RANGE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


def test_attention_job_uses_today_00_00_to_23_59_and_inbound_type():
    job = _job("attention")

    assert DATE_RANGE_RE.match(job.params["date_init"])
    assert job.params["date_init"].endswith("00:00")
    assert job.params["date_end"].endswith("23:59")
    assert job.params["type"] == "INBOUND"
    assert job.params["with_form"] == 1


def test_outbound_attention_job_differs_only_in_type():
    inbound = _job("attention")
    outbound = _job("outboundattention")

    assert inbound.endpoint == outbound.endpoint
    assert outbound.params["type"] == "OUTBOUND"
    diff_keys = {k for k in inbound.params if inbound.params[k] != outbound.params[k]}
    assert diff_keys == {"type"}


def test_call_incoming_job_has_vip_only_not_dialer_fields():
    job = _job("callincoming")

    assert job.params["typeExport"] == "incoming"
    assert job.params["with"] == "FORM"
    assert job.params["vip_only"] == "false"
    assert "manual_dialer_id" not in job.params


def test_call_outgoing_job_has_dialer_fields_not_vip_only():
    job = _job("calloutgoing")

    assert job.params["typeExport"] == "outgoing"
    assert job.params["manual_dialer_id"] == "0"
    assert job.params["dialer_id"] == "0"
    assert "vip_only" not in job.params


def test_contacts_job_has_no_date_range():
    job = _job("contacts")

    assert "date_init" not in job.params
    assert "date_end" not in job.params
    assert job.params["company_id"] == "ALL"


def test_transfer_job_uses_today_00_00_to_23_59_and_no_filters():
    job = _job("transfer")

    assert DATE_RANGE_RE.match(job.params["date_init"])
    assert job.params["date_init"].endswith("00:00")
    assert job.params["date_end"].endswith("23:59")
    assert job.endpoint == "/user/report_message/transfer/export"
    assert job.params["agent_id_origin"] == ""
    assert job.params["dest_type"] == ""
    assert job.params["status"] == ""


def test_build_jobs_file_date_defaults_to_today_for_every_job():
    for job in downloads.build_jobs():
        assert job.file_date == config.hoy()


def test_build_backfill_jobs_covers_the_five_dated_families_not_contacts():
    target = datetime.date(2026, 8, 10)

    jobs = downloads.build_backfill_jobs(target)

    assert {job.name for job in jobs} == {
        "attention",
        "outboundattention",
        "callincoming",
        "calloutgoing",
        "transfer",
    }


def test_build_backfill_jobs_requests_and_stamps_the_target_date_not_today():
    target = datetime.date(2026, 8, 10)

    jobs = downloads.build_backfill_jobs(target)

    for job in jobs:
        assert job.file_date == target
        assert job.params["date_init"] == "2026-08-10 00:00"
        assert job.params["date_end"] == "2026-08-10 23:59"


def test_filename_from_response_prefers_content_disposition():
    response = httpx.Response(
        200, headers={"content-disposition": 'attachment; filename="reporte.xlsx"'}
    )

    assert downloads._filename_from_response(response, fallback="x") == "reporte.xlsx"


def test_filename_from_response_falls_back_to_content_type_extension():
    response = httpx.Response(
        200, headers={"content-type": "application/vnd.ms-excel"}
    )

    assert downloads._filename_from_response(response, fallback="fallback") == "fallback.xls"


def test_filename_from_response_bare_fallback_when_no_hints():
    response = httpx.Response(200)

    assert downloads._filename_from_response(response, fallback="fallback") == "fallback"


@pytest.fixture
def isolated_downloads_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path)
    return tmp_path


def _client(handler) -> httpx.Client:
    return httpx.Client(base_url="https://fake.test", transport=httpx.MockTransport(handler))


def test_run_job_raises_download_error_on_html_response(isolated_downloads_dir):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>login</html>")

    job = downloads.DownloadJob(name="x", endpoint="/fake", params={})

    with pytest.raises(downloads.DownloadError):
        downloads.run_job(_client(handler), job)


def test_run_job_raises_download_error_on_empty_response(isolated_downloads_dir):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/vnd.ms-excel"}, content=b"")

    job = downloads.DownloadJob(name="x", endpoint="/fake", params={})

    with pytest.raises(downloads.DownloadError):
        downloads.run_job(_client(handler), job)


def test_run_job_raises_on_http_error_status(isolated_downloads_dir):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    job = downloads.DownloadJob(name="x", endpoint="/fake", params={})

    with pytest.raises(httpx.HTTPStatusError):
        downloads.run_job(_client(handler), job)


def test_run_job_success_writes_file_and_reports_timing(isolated_downloads_dir):
    body = b"contenido-del-excel"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "application/vnd.ms-excel",
                "content-disposition": 'attachment; filename="reporte.xls"',
            },
            content=body,
        )

    job = downloads.DownloadJob(name="attention", endpoint="/fake", params={"a": "1"})
    result = downloads.run_job(_client(handler), job)

    assert result.job is job
    assert result.status_code == 200
    assert result.size_bytes == len(body)
    assert result.elapsed_seconds >= 0
    assert result.path.exists()
    assert result.path.read_bytes() == body
    assert result.path.parent == isolated_downloads_dir


def test_run_job_names_the_file_after_the_jobs_file_date_not_todays_date(
    isolated_downloads_dir,
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "application/vnd.ms-excel",
                "content-disposition": 'attachment; filename="reporte.xls"',
            },
            content=b"x",
        )

    target = datetime.date(2026, 8, 10)
    job = downloads.DownloadJob(
        name="attention", endpoint="/fake", params={}, file_date=target
    )
    result = downloads.run_job(_client(handler), job)

    assert result.path.name == "attention_2026-08-10_reporte.xls"


def test_run_job_preserves_query_string_already_in_endpoint_when_params_empty(
    isolated_downloads_dir,
):
    seen_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, headers={"content-type": "application/zip"}, content=b"zip")

    endpoint = "https://fake.test/archivo.zip?X-Amz-Signature=abc123&X-Amz-Expires=432000"
    job = downloads.DownloadJob(name="attention_export", endpoint=endpoint, params={})

    downloads.run_job(_client(handler), job)

    assert "X-Amz-Signature=abc123" in seen_urls[0]


def test_latest_file_returns_none_when_nothing_downloaded_yet(isolated_downloads_dir):
    assert downloads.latest_file("attention") is None


def test_latest_file_ignores_other_report_names(isolated_downloads_dir):
    (isolated_downloads_dir / "contacts_2026-08-13_export.xlsx").write_bytes(b"x")

    assert downloads.latest_file("attention") is None


def test_latest_file_does_not_match_a_historical_backfill_file_of_the_same_name(
    isolated_downloads_dir,
):
    (
        isolated_downloads_dir / "attention_historical_2026-05-20_to_2026-08-18_export.xlsx"
    ).write_bytes(b"x")

    assert downloads.latest_file("attention") is None


def test_latest_file_picks_the_most_recently_modified_match(isolated_downloads_dir):
    older = isolated_downloads_dir / "attention_2026-08-11_a.xlsx"
    newer = isolated_downloads_dir / "attention_2026-08-13_b.xlsx"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")
    older_time = newer.stat().st_mtime - 100
    os.utime(older, (older_time, older_time))

    assert downloads.latest_file("attention") == newer


def test_all_files_returns_empty_list_when_nothing_downloaded_yet(
    isolated_downloads_dir,
):
    assert downloads.all_files("attention") == []


def test_all_files_ignores_other_report_names_and_historical_backfill_files(
    isolated_downloads_dir,
):
    (isolated_downloads_dir / "contacts_2026-08-13_export.xlsx").write_bytes(b"x")
    (
        isolated_downloads_dir / "attention_historical_2026-05-20_to_2026-08-18_export.xlsx"
    ).write_bytes(b"x")

    assert downloads.all_files("attention") == []


def test_build_historical_jobs_covers_the_five_dated_families_plus_contacts():
    date_init = datetime.date(2026, 5, 20)
    date_end = datetime.date(2026, 8, 18)

    jobs = downloads.build_historical_jobs(date_init, date_end)

    assert {job.name for job in jobs} == {
        "attention",
        "outboundattention",
        "callincoming",
        "calloutgoing",
        "transfer",
        "contacts",
    }


def test_build_historical_jobs_requests_the_wide_range_not_a_single_day():
    date_init = datetime.date(2026, 5, 20)
    date_end = datetime.date(2026, 8, 18)

    jobs = downloads.build_historical_jobs(date_init, date_end)

    for job in jobs:
        if job.name == "contacts":
            assert "date_init" not in job.params
            continue
        assert job.params["date_init"] == "2026-05-20 00:00"
        assert job.params["date_end"] == "2026-08-18 23:59"


def test_build_historical_jobs_labels_files_with_the_range_not_contacts():
    date_init = datetime.date(2026, 5, 20)
    date_end = datetime.date(2026, 8, 18)

    jobs = downloads.build_historical_jobs(date_init, date_end)

    for job in jobs:
        if job.name == "contacts":
            assert job.file_label is None
        else:
            assert job.file_label == "historical_2026-05-20_to_2026-08-18"
            assert job.file_date == date_end


def test_run_job_uses_file_label_instead_of_file_date_when_set(isolated_downloads_dir):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "application/vnd.ms-excel",
                "content-disposition": 'attachment; filename="reporte.xls"',
            },
            content=b"x",
        )

    job = downloads.DownloadJob(
        name="attention",
        endpoint="/fake",
        params={},
        file_date=datetime.date(2026, 8, 18),
        file_label="historical_2026-05-20_to_2026-08-18",
    )
    result = downloads.run_job(_client(handler), job)

    assert result.path.name == "attention_historical_2026-05-20_to_2026-08-18_reporte.xls"


def test_all_files_returns_every_days_file_oldest_first(isolated_downloads_dir):
    older = isolated_downloads_dir / "attention_2026-08-11_a.xlsx"
    newer = isolated_downloads_dir / "attention_2026-08-13_b.xlsx"
    newer.write_bytes(b"new")
    older.write_bytes(b"old")
    older_time = newer.stat().st_mtime - 100
    os.utime(older, (older_time, older_time))

    assert downloads.all_files("attention") == [older, newer]
