import logging
import jwt
import bcrypt
import datetime
import re
import secrets
from typing import Dict, Any
from pydantic import BaseModel, EmailStr, field_validator
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from app.core.config import get_settings, Settings
from app.core.postgres_client import PostgresClient
from app.api.dependencies import get_current_user
from app.core.security import limiter
from app.services.email_service import EmailService

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp_code: str

class ResendOTPRequest(BaseModel):
    email: EmailStr

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp_code: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
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

@router.post("/register", response_model=MessageResponse)
@limiter.limit("3/minute")
async def register(request: Request, user: UserRegister, background_tasks: BackgroundTasks, db: PostgresClient = Depends(get_db), email_service: EmailService = Depends(get_email_service)):
    existing = await db.select_by_eq("users", "email", user.email)
    
    hashed = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    if existing:
        if existing[0].get("is_verified"):
            raise HTTPException(status_code=400, detail="Email already registered")
        else:
            # Override Unverified logic
            await db.execute("UPDATE users SET password_hash = $1, name = $2 WHERE email = $3", hashed, user.name, user.email)
            await db.execute("DELETE FROM otps WHERE email = $1", user.email)
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

    otp_code = generate_otp()
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)
    
    otp_data = {
        "email": user.email,
        "otp_code": otp_code,
        "expires_at": expires_at
    }
    await db.insert("otps", otp_data)
    
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

    otps = await db.select_by_eq_ordered("otps", "email", verify_req.email, order_col="created_at", asc=False)
    if not otps:
        raise HTTPException(status_code=400, detail="No OTP found. Please resend.")
        
    latest_otp = otps[0]
    
    expires_at = datetime.datetime.fromisoformat(latest_otp["expires_at"].replace("Z", "+00:00"))
    if datetime.datetime.now(datetime.timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="OTP expired. Please resend.")
        
    if latest_otp["otp_code"] != verify_req.otp_code:
        raise HTTPException(status_code=400, detail="Invalid OTP code.")
        
    await db.execute("UPDATE users SET is_verified = TRUE WHERE email = $1", verify_req.email)
    await db.execute("DELETE FROM otps WHERE email = $1", verify_req.email)
    
    payload = {
        "sub": str(db_user["id"]),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    
    return {
        "access_token": token, 
        "token_type": "bearer",
        "user": {"id": str(db_user["id"]), "email": db_user["email"], "name": db_user["name"]}
    }

@router.post("/resend-otp", response_model=MessageResponse)
@limiter.limit("2/minute")
async def resend_otp(request: Request, resend_req: ResendOTPRequest, background_tasks: BackgroundTasks, db: PostgresClient = Depends(get_db), email_service: EmailService = Depends(get_email_service)):
    users = await db.select_by_eq("users", "email", resend_req.email)
    if not users:
        raise HTTPException(status_code=400, detail="Invalid request")
        
    if users[0].get("is_verified"):
        raise HTTPException(status_code=400, detail="User is already verified")

    # Enforce 60-second cooldown per email at database level
    otps = await db.select_by_eq_ordered("otps", "email", resend_req.email, order_col="created_at", asc=False)
    if otps:
        latest_otp = otps[0]
        created_at_val = latest_otp.get("created_at")
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

    await db.execute("DELETE FROM otps WHERE email = $1", resend_req.email)
    
    otp_code = generate_otp()
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)
    
    otp_data = {
        "email": resend_req.email,
        "otp_code": otp_code,
        "expires_at": expires_at
    }
    await db.insert("otps", otp_data)
    
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
        raise HTTPException(status_code=403, detail="Account not verified. Please verify your email first.")
    
    if not bcrypt.checkpw(user.password.encode('utf-8'), db_user["password_hash"].encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    payload = {
        "sub": str(db_user["id"]),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    
    return {
        "access_token": token, 
        "token_type": "bearer",
        "user": {"id": str(db_user["id"]), "email": db_user["email"], "name": db_user["name"]}
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
async def forgot_password(request: Request, req: ForgotPasswordRequest, background_tasks: BackgroundTasks, db: PostgresClient = Depends(get_db), email_service: EmailService = Depends(get_email_service)):
    users = await db.select_by_eq("users", "email", req.email)
    if not users:
        raise HTTPException(status_code=400, detail="Invalid email or user not found.")
        
    db_user = users[0]
    if not db_user.get("is_verified"):
        raise HTTPException(status_code=400, detail="Account is not verified yet. Please register or verify first.")

    # Enforce 60-second cooldown per email at database level
    otps = await db.select_by_eq_ordered("otps", "email", req.email, order_col="created_at", asc=False)
    if otps:
        latest_otp = otps[0]
        created_at_val = latest_otp.get("created_at")
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

    await db.execute("DELETE FROM otps WHERE email = $1", req.email)
    
    otp_code = generate_otp()
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)
    
    otp_data = {
        "email": req.email,
        "otp_code": otp_code,
        "expires_at": expires_at
    }
    await db.insert("otps", otp_data)
    
    background_tasks.add_task(email_service.send_reset_password_email, req.email, otp_code)
    
    return {"detail": "Reset password code sent to email."}

@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def reset_password(request: Request, req: ResetPasswordRequest, db: PostgresClient = Depends(get_db)):
    users = await db.select_by_eq("users", "email", req.email)
    if not users:
        raise HTTPException(status_code=400, detail="Invalid request")
        
    otps = await db.select_by_eq_ordered("otps", "email", req.email, order_col="created_at", asc=False)
    if not otps:
        raise HTTPException(status_code=400, detail="No reset code found. Please request a new code.")
        
    latest_otp = otps[0]
    
    expires_at = datetime.datetime.fromisoformat(latest_otp["expires_at"].replace("Z", "+00:00"))
    if datetime.datetime.now(datetime.timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Reset code expired. Please request a new code.")
        
    if latest_otp["otp_code"] != req.otp_code:
        raise HTTPException(status_code=400, detail="Invalid verification code.")
        
    new_pw_hash = bcrypt.hashpw(req.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    await db.execute("UPDATE users SET password_hash = $1 WHERE email = $2", new_pw_hash, req.email)
    await db.execute("DELETE FROM otps WHERE email = $1", req.email)
    
    return {"detail": "Password reset successfully. Please sign in."}
