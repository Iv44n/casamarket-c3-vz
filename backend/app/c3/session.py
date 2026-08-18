import httpx
from bs4 import BeautifulSoup

from .. import config


class AuthError(RuntimeError):
    pass


def _extract_token(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    token_input = soup.find("input", attrs={"name": "_token"})
    if token_input is None or not token_input.get("value"):
        raise AuthError(
            "No se encontro el campo _token en la pagina de login; "
            "puede que el formulario haya cambiado."
        )
    return token_input["value"]


def login(
    creds: config.Credentials,
    transport: httpx.BaseTransport | None = None,
    timeout: float = 30.0,
) -> httpx.Client:
    client = httpx.Client(
        base_url=creds.base_url, follow_redirects=True, timeout=timeout, transport=transport
    )

    login_page = client.get(config.LOGIN_PATH)
    login_page.raise_for_status()
    token = _extract_token(login_page.text)

    signin_response = client.post(
        config.SIGNIN_PATH,
        data={
            "_token": token,
            "username": creds.username,
            "password": creds.password,
        },
    )
    signin_response.raise_for_status()

    if not is_authenticated(client):
        client.close()
        raise AuthError(
            "El login no dejo una sesion valida (usuario o clave incorrectos, "
            "o el sistema no autorizo el acceso)."
        )

    return client


def is_authenticated(client: httpx.Client) -> bool:
    probe_path = next(iter(config.REPORT_PATHS.values()))
    response = client.get(probe_path, follow_redirects=False)

    if response.status_code == 302:
        location = response.headers.get("location", "")
        return config.LOGIN_PATH not in location

    return response.status_code == 200
