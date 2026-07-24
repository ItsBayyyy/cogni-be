import logging
import jwt
import bcrypt
import datetime
from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.config import get_settings, Settings
from app.core.postgres_client import PostgresClient
from app.api.dependencies import get_current_user

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict

def get_db(settings: Settings = Depends(get_settings)) -> PostgresClient:
    return PostgresClient(url=settings.DATABASE_URL)

@router.post("/register", response_model=TokenResponse)
async def register(user: UserRegister, db: PostgresClient = Depends(get_db), settings: Settings = Depends(get_settings)):
    existing = await db.select_by_eq("users", "email", user.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    user_data = {
        "email": user.email,
        "password_hash": hashed,
        "name": user.name
    }
    
    new_user = await db.insert("users", user_data)
    if not new_user:
        raise HTTPException(status_code=500, detail="Failed to create user")

    payload = {
        "sub": str(new_user["id"]),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    
    return {
        "access_token": token, 
        "token_type": "bearer",
        "user": {"id": str(new_user["id"]), "email": new_user["email"], "name": new_user["name"]}
    }

@router.post("/login", response_model=TokenResponse)
async def login(user: UserLogin, db: PostgresClient = Depends(get_db), settings: Settings = Depends(get_settings)):
    users = await db.select_by_eq("users", "email", user.email)
    if not users:
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    db_user = users[0]
    
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
