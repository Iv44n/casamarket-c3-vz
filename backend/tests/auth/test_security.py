from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth import security


def test_hash_password_then_verify_with_the_same_password_succeeds():
    password_hash = security.hash_password("correcthorsebattery")

    assert security.verify_password("correcthorsebattery", password_hash)


def test_verify_password_fails_for_a_wrong_password():
    password_hash = security.hash_password("correcthorsebattery")

    assert not security.verify_password("wrong-password", password_hash)


def test_create_access_token_then_decode_returns_the_same_claims():
    token, expires_at = security.create_access_token(
        user_id=1, username="ana", is_admin=True, secret="test-secret-that-is-long-enough-1234"
    )

    payload = security.decode_access_token(token, "test-secret-that-is-long-enough-1234")

    assert payload.user_id == 1
    assert payload.username == "ana"
    assert payload.is_admin is True
    assert expires_at.tzinfo is not None


def test_decode_access_token_raises_for_a_token_signed_with_a_different_secret():
    token, _ = security.create_access_token(1, "ana", False, "test-secret-that-is-long-enough-1234")

    with pytest.raises(jwt.PyJWTError):
        security.decode_access_token(token, "a-different-secret-that-is-long-enough-5678")


def test_decode_access_token_raises_for_an_expired_token():
    expired_payload = {
        "sub": 1,
        "username": "ana",
        "is_admin": False,
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    token = jwt.encode(expired_payload, "test-secret-that-is-long-enough-1234", algorithm="HS256")

    with pytest.raises(jwt.PyJWTError):
        security.decode_access_token(token, "test-secret-that-is-long-enough-1234")
