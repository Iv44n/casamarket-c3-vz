import json
from dataclasses import dataclass

import httpx

from .. import config
from . import downloads, reports

_JSON_HEADERS = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}

_OTHER_DIRECTION = {
    "attention": "outboundattention",
    "outboundattention": "attention",
}


class MassiveError(RuntimeError):
    pass


@dataclass(frozen=True)
class _State:
    name: str
    job_id: int


@dataclass(frozen=True)
class CycleResult:
    action: str
    name: str
    job_id: int | None = None
    status: str | None = None
    note: str | None = None
    result: downloads.DownloadResult | None = None
    next_name: str | None = None
    next_job_id: int | None = None


def _load_state() -> _State | None:
    if not config.MASSIVE_STATE_FILE.exists():
        return None
    data = json.loads(config.MASSIVE_STATE_FILE.read_text(encoding="utf-8"))
    return _State(name=data["name"], job_id=data["job_id"])


def _save_state(state: _State) -> None:
    config.MASSIVE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.MASSIVE_STATE_FILE.write_text(
        json.dumps({"name": state.name, "job_id": state.job_id}), encoding="utf-8"
    )


def _clear_state() -> None:
    config.MASSIVE_STATE_FILE.unlink(missing_ok=True)


def _list_jobs(client: httpx.Client) -> list[dict]:
    response = client.get(reports.MASSIVE_LIST_ENDPOINT, headers=_JSON_HEADERS)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as exc:
        raise MassiveError(
            f"get_massives no devolvio JSON (¿falto el header Accept?): "
            f"{response.text[:200]!r}"
        ) from exc


def _trigger(client: httpx.Client, name: str) -> None:
    mechanism = reports.EXPORT_MECHANISMS[name]
    params = downloads.attention_base_params(mechanism.type_param_value)
    params["with_form"] = 0

    response = client.get(mechanism.massive_endpoint, params=params, headers=_JSON_HEADERS)
    response.raise_for_status()
    try:
        body = response.json()
    except ValueError as exc:
        raise MassiveError(
            f"El trigger de '{name}' no devolvio JSON: {response.text[:200]!r}"
        ) from exc
    if not body.get("success", True):
        raise MassiveError(f"El servidor rechazo el job masivo de '{name}': {body}")


def _trigger_and_track(client: httpx.Client, name: str) -> _State:
    before_ids = {job["id"] for job in _list_jobs(client)}
    _trigger(client, name)

    new_ids = {job["id"] for job in _list_jobs(client)} - before_ids
    if not new_ids:
        raise MassiveError(
            f"Se disparo el job masivo de '{name}' pero no aparecio ninguno "
            f"nuevo en get_massives."
        )
    state = _State(name=name, job_id=max(new_ids))
    _save_state(state)
    return state


def _download(client: httpx.Client, name: str, download_url: str) -> downloads.DownloadResult:
    job = downloads.DownloadJob(name=f"{name}_masivo", endpoint=download_url, params={})
    return downloads.run_job(client, job)


def run_cycle(client: httpx.Client) -> CycleResult:
    state = _load_state()
    if state is None:
        triggered = _trigger_and_track(client, "attention")
        return CycleResult(action="triggered", name=triggered.name, job_id=triggered.job_id)

    jobs = _list_jobs(client)
    job = next((j for j in jobs if j["id"] == state.job_id), None)

    if job is None or job["status"] == "FAILED":
        note = job.get("error_message") if job else "ya no aparece en get_massives (¿expiro?)"
        _clear_state()
        retried = _trigger_and_track(client, state.name)
        return CycleResult(
            action="retried", name=retried.name, job_id=retried.job_id, note=note
        )

    if job["status"] != "COMPLETED":
        return CycleResult(action="waiting", name=state.name, job_id=state.job_id, status=job["status"])

    result = _download(client, state.name, job["download_url"])
    _clear_state()
    next_name = _OTHER_DIRECTION[state.name]
    triggered = _trigger_and_track(client, next_name)
    return CycleResult(
        action="downloaded",
        name=state.name,
        result=result,
        next_name=triggered.name,
        next_job_id=triggered.job_id,
    )


def describe(cycle: CycleResult) -> str:
    if cycle.action == "triggered":
        return f"se encolo el reporte masivo de '{cycle.name}' (job #{cycle.job_id})"
    if cycle.action == "waiting":
        return f"el reporte masivo de '{cycle.name}' (job #{cycle.job_id}) sigue {cycle.status}"
    if cycle.action == "retried":
        return (
            f"el job anterior de '{cycle.name}' no se pudo completar ({cycle.note}); "
            f"se volvio a encolar (job #{cycle.job_id})"
        )
    if cycle.action == "downloaded":
        return (
            f"se descargo el reporte masivo de '{cycle.name}' -> {cycle.result.path.name} "
            f"({cycle.result.size_bytes} bytes); se encolo '{cycle.next_name}' "
            f"(job #{cycle.next_job_id})"
        )
    raise ValueError(f"CycleResult.action desconocido: {cycle.action!r}")
