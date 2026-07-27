import datetime

import jwt
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request
from unittest.mock import AsyncMock

from app.api.v1.routers.auth import create_access_token, otp_digest, verify_otp_value
from app.core.config import Settings
from app.core.postgres_client import PostgresClient
from app.core.security import get_real_ip
from app.schemas.transcript import MessageRequest


def settings() -> Settings:
    return Settings(
        GROQ_API_KEY="test",
        DATABASE_URL="postgresql://test",
        JWT_SECRET="j" * 64,
        OTP_PEPPER="p" * 64,
    )


def test_access_token_requires_enterprise_claims():
    cfg = settings()
    token = create_access_token(
        {"id": "user-123", "token_version": 4},
        cfg,
    )
    payload = jwt.decode(
        token,
        cfg.JWT_SECRET,
        algorithms=["HS256"],
        issuer=cfg.JWT_ISSUER,
        audience=cfg.JWT_AUDIENCE,
    )
    assert payload["sub"] == "user-123"
    assert payload["ver"] == 4
    assert payload["type"] == "access"
    assert {"iat", "exp", "iss", "aud", "jti"} <= payload.keys()


def test_otp_digest_is_purpose_bound_and_does_not_store_code():
    cfg = settings()
    verify_digest = otp_digest(cfg, "User@Example.com", "verify", "123456")
    reset_digest = otp_digest(cfg, "User@Example.com", "reset", "123456")
    assert verify_digest != reset_digest
    assert "123456" not in verify_digest
    assert len(verify_digest) == 64


@pytest.mark.asyncio
async def test_wrong_otp_increments_persistent_attempt_counter():
    cfg = settings()
    db = AsyncMock(spec=PostgresClient)
    db.fetchrow.return_value = {
        "id": "otp-1",
        "otp_digest": otp_digest(cfg, "user@example.com", "reset", "654321"),
        "attempts": 0,
        "expires_at": (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
        ).isoformat(),
    }

    with pytest.raises(HTTPException) as exc:
        await verify_otp_value(
            db,
            cfg,
            "user@example.com",
            "reset",
            "000000",
        )

    assert exc.value.status_code == 400
    db.execute.assert_awaited_once()


def test_untrusted_client_cannot_spoof_forwarded_for():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", b"203.0.113.50")],
            "client": ("198.51.100.10", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )
    assert get_real_ip(request) == "198.51.100.10"


def test_client_role_is_not_part_of_message_contract():
    with pytest.raises(ValidationError):
        MessageRequest.model_validate(
            {"content": "hello", "role": "professor_agent"}
        )
