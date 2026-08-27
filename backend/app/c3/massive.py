import time

import httpx

from .. import config
from . import downloads, reports, session

_JSON_HEADERS = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}


class MassiveError(RuntimeError):
    pass


class C3Session:
    """Envuelve un httpx.Client re-logueable. Confirmado en vivo contra C3 (2026-08-26):
    la cuenta solo puede tener UNA sesion activa a la vez -- loguearse de nuevo con la
    misma cuenta invalida al instante cualquier sesion anterior, sin logout explicito y
    sin aviso. Una corrida de benchmarks mantiene un cliente vivo mientras espera el
    reporte masivo (puede tardar horas, segun la propia advertencia de C3); si en el medio
    el refresh regular (cada 5 min) u otra corrida cualquiera se loguea con la misma
    cuenta, esta sesion queda invalidada y la siguiente request revienta con 401. Las
    funciones de este modulo detectan ese 401 y llaman relogin() para recuperarse en vez
    de tirar toda la corrida por la borda."""

    def __init__(
        self,
        creds: config.Credentials,
        *,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ):
        self._creds = creds
        self._transport = transport
        self.client = client or session.login(creds, transport=transport)

    def relogin(self) -> None:
        old_client = self.client
        self.client = session.login(self._creds, transport=self._transport)
        old_client.close()

    def close(self) -> None:
        self.client.close()


def _get_with_relogin(sess: C3Session, url: str, **kwargs) -> httpx.Response:
    """GET tolerante a que C3 haya invalidado la sesion actual (ver C3Session) -- un 401
    dispara UN relogin y un solo reintento; una segunda falla ya se deja propagar."""
    response = sess.client.get(url, **kwargs)
    if response.status_code == 401:
        sess.relogin()
        response = sess.client.get(url, **kwargs)
    return response


def _list_jobs(sess: C3Session) -> list[dict]:
    response = _get_with_relogin(sess, reports.MASSIVE_LIST_ENDPOINT, headers=_JSON_HEADERS)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as exc:
        raise MassiveError(
            f"get_massives no devolvio JSON (¿falto el header Accept?): "
            f"{response.text[:200]!r}"
        ) from exc


def _trigger(sess: C3Session, name: str) -> None:
    mechanism = reports.EXPORT_MECHANISMS[name]
    params = downloads.attention_base_params(mechanism.type_param_value)
    params["with_form"] = 0

    response = _get_with_relogin(
        sess, mechanism.massive_endpoint, params=params, headers=_JSON_HEADERS
    )
    response.raise_for_status()
    try:
        body = response.json()
    except ValueError as exc:
        raise MassiveError(
            f"El trigger de '{name}' no devolvio JSON: {response.text[:200]!r}"
        ) from exc
    if not body.get("success", True):
        raise MassiveError(f"El servidor rechazo el job masivo de '{name}': {body}")


def trigger_and_track(sess: C3Session, name: str) -> int:
    """Dispara el reporte masivo de `name` y devuelve el id del job nuevo que aparece en
    get_massives. Sin persistencia a archivo -- el llamador (wait_for_completion) guarda
    el id en una variable local, no algo que deba sobrevivir entre llamadas HTTP."""
    before_ids = {job["id"] for job in _list_jobs(sess)}
    _trigger(sess, name)

    new_ids = {job["id"] for job in _list_jobs(sess)} - before_ids
    if not new_ids:
        raise MassiveError(
            f"Se disparo el job masivo de '{name}' pero no aparecio ninguno "
            f"nuevo en get_massives."
        )
    return max(new_ids)


def download(sess: C3Session, name: str, download_url: str) -> downloads.DownloadResult:
    job = downloads.DownloadJob(name=f"{name}_masivo", endpoint=download_url, params={})
    try:
        return downloads.run_job(sess.client, job)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 401:
            raise
        sess.relogin()
        return downloads.run_job(sess.client, job)


def wait_for_completion(
    sess: C3Session,
    name: str,
    job_id: int,
    *,
    poll_interval_seconds: float,
    timeout_seconds: float,
    sleep=time.sleep,
) -> dict:
    """Hace polling de get_massives hasta que `job_id` este COMPLETED. Si aparece FAILED o
    directamente deja de listarse (¿expiro?), reintenta UNA vez bajo el mismo rol (`name`) y
    sigue esperando bajo el id nuevo -- una segunda falla ya no reintenta, para no encolar
    reportes masivos indefinidamente si algo esta genuinamente roto del lado de C3. La
    sesion invalidada (401) se maneja aparte, dentro de cada llamada a _list_jobs/_trigger
    (ver C3Session) -- no cuenta como este tipo de "fallo del reporte" ni consume el
    reintento de arriba."""
    deadline = time.monotonic() + timeout_seconds
    current_id = job_id
    retried = False

    while True:
        jobs = _list_jobs(sess)
        job = next((j for j in jobs if j["id"] == current_id), None)

        if job is not None and job["status"] == "COMPLETED":
            return job

        if job is None or job["status"] == "FAILED":
            if retried:
                note = job.get("error_message") if job else "ya no aparece en get_massives"
                raise MassiveError(
                    f"El reporte masivo de '{name}' (job #{current_id}) fallo dos veces "
                    f"seguidas -- {note}."
                )
            retried = True
            current_id = trigger_and_track(sess, name)
            continue

        if time.monotonic() >= deadline:
            raise MassiveError(
                f"El reporte masivo de '{name}' (job #{current_id}) no completo dentro de "
                f"{timeout_seconds:.0f}s (ultimo status: {job['status']!r})."
            )
        sleep(poll_interval_seconds)


def run_direction(
    sess: C3Session,
    name: str,
    *,
    poll_interval_seconds: float,
    timeout_seconds: float,
    sleep=time.sleep,
) -> downloads.DownloadResult:
    """trigger_and_track -> wait_for_completion -> download, bloqueante. La unica funcion
    publica que el pipeline de benchmarks necesita llamar por direccion."""
    job_id = trigger_and_track(sess, name)
    job = wait_for_completion(
        sess,
        name,
        job_id,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
        sleep=sleep,
    )
    return download(sess, name, job["download_url"])
