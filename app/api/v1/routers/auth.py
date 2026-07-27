import logging
import jwt
import bcrypt
import datetime
import hashlib
import hmac
import re
import secrets
import uuid
from pydantic import BaseModel, EmailStr, Field, field_validator
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from app.core.config import get_settings, Settings
from app.core.postgres_client import PostgresClient
from app.api.dependencies import get_current_user
from app.core.security import limiter
from app.services.email_service import EmailService

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

class UserRegister(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank")
        return value

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(pattern=r"^\d{6}$")

class ResendOTPRequest(BaseModel):
    email: EmailStr

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class VerifyResetOTPRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(pattern=r"^\d{6}$")

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp_code: str = Field(pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return v

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict

class MessageResponse(BaseModel):
    detail: str

def get_db(settings: Settings = Depends(get_settings)) -> PostgresClient:
    return PostgresClient(url=settings.DATABASE_URL)

def get_email_service(settings: Settings = Depends(get_settings)) -> EmailService:
    return EmailService(settings=settings)

def generate_otp() -> str:
    return str(secrets.randbelow(900000) + 100000)

def otp_digest(settings: Settings, email: str, purpose: str, otp_code: str) -> str:
    message = f"{purpose}:{email.lower()}:{otp_code}".encode("utf-8")
    return hmac.new(settings.OTP_PEPPER.encode("utf-8"), message, hashlib.sha256).hexdigest()

def create_access_token(user: dict, settings: Settings) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "iat": now,
        "exp": now + datetime.timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "ver": int(user.get("token_version") or 0),
        "type": "access",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

async def delete_otps(db: PostgresClient, email: str, purpose: str) -> None:
    await db.execute(
        "DELETE FROM otps WHERE email = $1 AND purpose = $2",
        email,
        purpose,
    )

async def create_otp(
    db: PostgresClient,
    settings: Settings,
    email: str,
    purpose: str,
) -> str:
    await delete_otps(db, email, purpose)
    otp_code = generate_otp()
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)
    await db.insert(
        "otps",
        {
            "email": email,
            "otp_digest": otp_digest(settings, email, purpose, otp_code),
            "purpose": purpose,
            "attempts": 0,
            "expires_at": expires_at,
        },
    )
    return otp_code

async def latest_otp(db: PostgresClient, email: str, purpose: str):
    return await db.fetchrow(
        """
        SELECT * FROM otps
        WHERE email = $1 AND purpose = $2 AND consumed_at IS NULL
        ORDER BY created_at DESC
        LIMIT 1
        """,
        email,
        purpose,
    )

async def verify_otp_value(
    db: PostgresClient,
    settings: Settings,
    email: str,
    purpose: str,
    otp_code: str,
) -> dict:
    record = await latest_otp(db, email, purpose)
    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    if int(record.get("attempts") or 0) >= 5:
        raise HTTPException(status_code=429, detail="Too many verification attempts")

    expires_at = datetime.datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
    if datetime.datetime.now(datetime.timezone.utc) > expires_at:
        await delete_otps(db, email, purpose)
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    supplied_digest = otp_digest(settings, email, purpose, otp_code)
    if not hmac.compare_digest(record["otp_digest"], supplied_digest):
        await db.execute(
            "UPDATE otps SET attempts = LEAST(attempts + 1, 5) WHERE id = $1",
            record["id"],
        )
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")
    return record

@router.post("/register", response_model=MessageResponse)
@limiter.limit("3/minute")
async def register(
    request: Request,
    user: UserRegister,
    background_tasks: BackgroundTasks,
    db: PostgresClient = Depends(get_db),
    email_service: EmailService = Depends(get_email_service),
    settings: Settings = Depends(get_settings),
):
    existing = await db.select_by_eq("users", "email", user.email)
    
    hashed = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    if existing:
        if existing[0].get("is_verified"):
            return {"detail": "If registration can proceed, a verification code will be sent."}
        else:
            # Override Unverified logic
            await db.execute("UPDATE users SET password_hash = $1, name = $2 WHERE email = $3", hashed, user.name, user.email)
            await delete_otps(db, user.email, "verify")
    else:
        user_data = {
            "email": user.email,
            "password_hash": hashed,
            "name": user.name,
            "is_verified": False
        }
        new_user = await db.insert("users", user_data)
        if not new_user:
            raise HTTPException(status_code=500, detail="Failed to create user")

    otp_code = await create_otp(db, settings, user.email, "verify")
    
    background_tasks.add_task(email_service.send_otp_email, user.email, otp_code)
    
    return {"detail": "OTP sent to email. Please verify."}


@router.post("/verify-otp", response_model=TokenResponse)
@limiter.limit("5/minute")
async def verify_otp(request: Request, verify_req: VerifyOTPRequest, db: PostgresClient = Depends(get_db), settings: Settings = Depends(get_settings)):
    users = await db.select_by_eq("users", "email", verify_req.email)
    if not users:
        raise HTTPException(status_code=400, detail="Invalid request")
        
    db_user = users[0]
    if db_user.get("is_verified"):
        raise HTTPException(status_code=400, detail="User is already verified")

    otp_record = await verify_otp_value(
        db,
        settings,
        verify_req.email,
        "verify",
        verify_req.otp_code,
    )
        
    await db.execute("UPDATE users SET is_verified = TRUE WHERE email = $1", verify_req.email)
    await db.execute(
        "UPDATE otps SET consumed_at = CURRENT_TIMESTAMP WHERE id = $1",
        otp_record["id"],
    )
    db_user["is_verified"] = True
    token = create_access_token(db_user, settings)
    
    return {
        "access_token": token, 
        "token_type": "bearer",
        "user": {"id": str(db_user["id"]), "email": db_user["email"], "name": db_user["name"]}
    }

@router.post("/resend-otp", response_model=MessageResponse)
@limiter.limit("2/minute")
async def resend_otp(
    request: Request,
    resend_req: ResendOTPRequest,
    background_tasks: BackgroundTasks,
    db: PostgresClient = Depends(get_db),
    email_service: EmailService = Depends(get_email_service),
    settings: Settings = Depends(get_settings),
):
    users = await db.select_by_eq("users", "email", resend_req.email)
    if not users:
        raise HTTPException(status_code=400, detail="Invalid request")
        
    if users[0].get("is_verified"):
        raise HTTPException(status_code=400, detail="User is already verified")

    # Enforce 60-second cooldown per email at database level
    existing_otp = await latest_otp(db, resend_req.email, "verify")
    if existing_otp:
        created_at_val = existing_otp.get("created_at")
        if created_at_val:
            if isinstance(created_at_val, str):
                created_at = datetime.datetime.fromisoformat(created_at_val.replace("Z", "+00:00"))
            else:
                created_at = created_at_val
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=datetime.timezone.utc)
            
            elapsed = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
            if elapsed < 60:
                remaining = int(60 - elapsed)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Please wait {remaining} seconds before requesting a new OTP code."
                )

    otp_code = await create_otp(db, settings, resend_req.email, "verify")
    
    background_tasks.add_task(email_service.send_otp_email, resend_req.email, otp_code)
    
    return {"detail": "New OTP sent to email."}

@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, user: UserLogin, db: PostgresClient = Depends(get_db), settings: Settings = Depends(get_settings)):
    users = await db.select_by_eq("users", "email", user.email)
    if not users:
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    db_user = users[0]
    
    if not db_user.get("is_verified"):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if len(user.password.encode("utf-8")) > 72 or not bcrypt.checkpw(
        user.password.encode("utf-8"),
        db_user["password_hash"].encode("utf-8"),
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(db_user, settings)
    
    return {
        "access_token": token, 
        "token_type": "bearer",
        "user": {"id": str(db_user["id"]), "email": db_user["email"], "name": db_user["name"]}
    }


@router.post("/demo", response_model=TokenResponse)
@limiter.limit("10/hour")
async def demo_login(
    request: Request,
    db: PostgresClient = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.DEMO_LOGIN_ENABLED:
        raise HTTPException(status_code=404, detail="Demo access is unavailable")

    # Opportunistic cleanup. Demo users own only their isolated sessions, and
    # cascading foreign keys remove their transcripts as well.
    await db.execute(
        """
        DELETE FROM users
        WHERE email LIKE 'demo-%@demo.cogniflip.invalid'
          AND created_at < CURRENT_TIMESTAMP - INTERVAL '6 hours'
        """
    )

    demo_id = str(uuid.uuid4())
    demo_email = f"demo-{demo_id}@demo.cogniflip.invalid"
    random_password = secrets.token_urlsafe(48).encode("utf-8")
    password_hash = bcrypt.hashpw(random_password, bcrypt.gensalt()).decode("utf-8")
    db_user = await db.insert(
        "users",
        {
            "id": demo_id,
            "email": demo_email,
            "password_hash": password_hash,
            "name": "Demo Judge",
            "is_verified": True,
            "token_version": 0,
        },
    )
    if not db_user:
        raise HTTPException(status_code=503, detail="Demo access is unavailable")

    token = create_access_token(db_user, settings)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(db_user["id"]),
            "email": db_user["email"],
            "name": db_user["name"],
        },
    }

@router.get("/me")
async def get_me(db: PostgresClient = Depends(get_db), current_user_id: str = Depends(get_current_user)):
    users = await db.select_by_eq("users", "id", current_user_id)
    if not users:
        raise HTTPException(status_code=404, detail="User not found")
    db_user = users[0]
    return {"id": str(db_user["id"]), "email": db_user["email"], "name": db_user["name"]}

@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    req: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: PostgresClient = Depends(get_db),
    email_service: EmailService = Depends(get_email_service),
    settings: Settings = Depends(get_settings),
):
    users = await db.select_by_eq("users", "email", req.email)
    if not users:
        return {"detail": "If the account exists, reset instructions will be sent."}
        
    db_user = users[0]
    if not db_user.get("is_verified"):
        return {"detail": "If the account exists, reset instructions will be sent."}

    # Enforce 60-second cooldown per email at database level
    existing_otp = await latest_otp(db, req.email, "reset")
    if existing_otp:
        created_at_val = existing_otp.get("created_at")
        if created_at_val:
            if isinstance(created_at_val, str):
                created_at = datetime.datetime.fromisoformat(created_at_val.replace("Z", "+00:00"))
            else:
                created_at = created_at_val
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=datetime.timezone.utc)
            
            elapsed = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
            if elapsed < 60:
                remaining = int(60 - elapsed)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Please wait {remaining} seconds before requesting a new reset code."
                )

    otp_code = await create_otp(db, settings, req.email, "reset")
    
    background_tasks.add_task(email_service.send_reset_password_email, req.email, otp_code)
    
    return {"detail": "If the account exists, reset instructions will be sent."}

@router.post("/verify-reset-otp", response_model=MessageResponse)
@limiter.limit("5/minute")
async def verify_reset_otp(
    request: Request,
    req: VerifyResetOTPRequest,
    db: PostgresClient = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    users = await db.select_by_eq("users", "email", req.email)
    if not users:
        raise HTTPException(status_code=400, detail="Invalid request")
        
    await verify_otp_value(db, settings, req.email, "reset", req.otp_code)
        
    return {"detail": "Reset code verified."}

@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    req: ResetPasswordRequest,
    db: PostgresClient = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    users = await db.select_by_eq("users", "email", req.email)
    if not users:
        raise HTTPException(status_code=400, detail="Invalid request")
        
    otp_record = await verify_otp_value(db, settings, req.email, "reset", req.otp_code)
        
    new_pw_hash = bcrypt.hashpw(req.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    await db.execute(
        """
        UPDATE users
        SET password_hash = $1, token_version = token_version + 1
        WHERE email = $2
        """,
        new_pw_hash,
        req.email,
    )
    await db.execute(
        "UPDATE otps SET consumed_at = CURRENT_TIMESTAMP WHERE id = $1",
        otp_record["id"],
    )
    
    return {"detail": "Password reset successfully. Please sign in."}
