import httpx
import pytest

from app import config
from app.c3 import session

LOGIN_HTML = '<input name="_token" value="tok-123" autocomplete="off">'
LOGIN_HTML_SIN_TOKEN = "<p>no hay token aqui</p>"


def _creds() -> config.Credentials:
    return config.Credentials(base_url="https://fake.test", username="user", password="pass")


def test_extract_token_found():
    assert session._extract_token(LOGIN_HTML) == "tok-123"


def test_extract_token_missing_raises():
    with pytest.raises(session.AuthError):
        session._extract_token(LOGIN_HTML_SIN_TOKEN)


def test_is_authenticated_true_on_200():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="ok"))
    client = httpx.Client(base_url="https://fake.test", transport=transport)

    assert session.is_authenticated(client) is True


def test_is_authenticated_false_on_redirect_to_login():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": config.LOGIN_PATH})

    client = httpx.Client(base_url="https://fake.test", transport=httpx.MockTransport(handler))

    assert session.is_authenticated(client) is False


def test_is_authenticated_true_on_redirect_elsewhere():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/user/dashboard"})

    client = httpx.Client(base_url="https://fake.test", transport=httpx.MockTransport(handler))

    assert session.is_authenticated(client) is True


def _login_handler(probe_redirects_to_login: bool):
    probe_path = next(iter(config.REPORT_PATHS.values()))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == config.LOGIN_PATH and request.method == "GET":
            return httpx.Response(200, text=LOGIN_HTML)
        if request.url.path == config.SIGNIN_PATH and request.method == "POST":
            return httpx.Response(302, headers={"location": "/user"})
        if request.url.path == "/user" and request.method == "GET":
            return httpx.Response(200, text="dashboard")
        if request.url.path == probe_path:
            if probe_redirects_to_login:
                return httpx.Response(302, headers={"location": config.LOGIN_PATH})
            return httpx.Response(200, text="ok")
        return httpx.Response(404)

    return handler


def test_login_success_returns_authenticated_client():
    transport = httpx.MockTransport(_login_handler(probe_redirects_to_login=False))

    client = session.login(_creds(), transport=transport)

    assert isinstance(client, httpx.Client)
    client.close()


def test_login_bad_credentials_raises_autherror():
    transport = httpx.MockTransport(_login_handler(probe_redirects_to_login=True))

    with pytest.raises(session.AuthError):
        session.login(_creds(), transport=transport)


def test_login_missing_token_raises_autherror():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == config.LOGIN_PATH:
            return httpx.Response(200, text=LOGIN_HTML_SIN_TOKEN)
        return httpx.Response(404)

    with pytest.raises(session.AuthError):
        session.login(_creds(), transport=httpx.MockTransport(handler))
