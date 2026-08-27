import pytest

from app.auth import rate_limit


@pytest.fixture(autouse=True)
def clean_rate_limit_state():
    rate_limit._failed_attempts.clear()
    yield
    rate_limit._failed_attempts.clear()


def test_check_does_not_raise_below_the_attempt_limit():
    for _ in range(rate_limit._MAX_ATTEMPTS - 1):
        rate_limit.record_failure("ana")

    rate_limit.check("ana")  # no debe lanzar


def test_check_raises_once_the_attempt_limit_is_reached():
    for _ in range(rate_limit._MAX_ATTEMPTS):
        rate_limit.record_failure("ana")

    with pytest.raises(rate_limit.TooManyAttemptsError):
        rate_limit.check("ana")


def test_clear_resets_the_counter():
    for _ in range(rate_limit._MAX_ATTEMPTS):
        rate_limit.record_failure("ana")

    rate_limit.clear("ana")

    rate_limit.check("ana")  # no debe lanzar


def test_attempts_outside_the_window_are_ignored(monkeypatch: pytest.MonkeyPatch):
    now = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])

    for _ in range(rate_limit._MAX_ATTEMPTS):
        rate_limit.record_failure("ana")

    now[0] += rate_limit._WINDOW_SECONDS + 1

    rate_limit.check("ana")  # los intentos viejos ya expiraron, no debe lanzar


def test_different_keys_are_tracked_independently():
    for _ in range(rate_limit._MAX_ATTEMPTS):
        rate_limit.record_failure("ana")

    rate_limit.check("luis")  # no debe lanzar -- distinta key
