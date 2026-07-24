from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api.v1.routers import health, session, voice, auth
from app.services.transcript_service import TranscriptService

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await TranscriptService.init_fallback_db()
    yield

# 1. INISIALISASI APP TERLEBIH DAHULU
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Async-first FastAPI backend for Student/Professor AI Agents.",
    lifespan=lifespan  
)

# 2. TAMBAHKAN CORS MIDDLEWARE SETELAH APP DIBUAT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # atau spesifik: ["http://localhost:3000", "https://your-v0-preview.vercel.app"]
    allow_credentials=True,
    allow_methods=["*"],   # WAJIB include OPTIONS
    allow_headers=["*"],   # WAJIB allow Authorization header
)

# 3. MASUKKAN ROUTER
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(session.router, prefix="/api/v1/sessions", tags=["sessions"])
app.include_router(voice.router, prefix="/api/v1/voice")