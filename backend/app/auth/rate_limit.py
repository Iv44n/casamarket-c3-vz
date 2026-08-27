import threading
import time

_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 15 * 60

_failed_attempts: dict[str, list[float]] = {}
_lock = threading.Lock()


class TooManyAttemptsError(Exception):
    pass


def check(key: str) -> None:
    """Lanza TooManyAttemptsError si `key` (username normalizado) acumulo >= _MAX_ATTEMPTS
    logins fallidos en los ultimos _WINDOW_SECONDS. Estado en memoria de proceso, mismo
    espiritu que extraction/state.py's threading.Lock -- consistente con que este server corre
    en un unico proceso, sin --workers (ver CLAUDE.md)."""
    now = time.monotonic()
    with _lock:
        attempts = [t for t in _failed_attempts.get(key, []) if now - t < _WINDOW_SECONDS]
        _failed_attempts[key] = attempts
        if len(attempts) >= _MAX_ATTEMPTS:
            raise TooManyAttemptsError(
                f"Demasiados intentos fallidos para {key!r}. Espera unos minutos e intenta de nuevo."
            )


def record_failure(key: str) -> None:
    with _lock:
        _failed_attempts.setdefault(key, []).append(time.monotonic())


def clear(key: str) -> None:
    with _lock:
        _failed_attempts.pop(key, None)
