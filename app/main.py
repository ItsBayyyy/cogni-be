import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.security import limiter
from app.core.config import get_settings
from app.api.v1.routers import health, session, voice, auth
from app.services.transcript_service import TranscriptService

settings = get_settings()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await TranscriptService.init_fallback_db()
    yield

# 1. INISIALISASI APP TERLEBIH DAHULU
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Async-first FastAPI backend for Student/Professor AI Agents.",
    docs_url=None,       # Disable Swagger UI in production
    redoc_url=None,      # Disable ReDoc in production
    openapi_url=None,    # Disable OpenAPI schema in production
    lifespan=lifespan  
)

# 2. TAMBAHKAN CORS MIDDLEWARE SETELAH APP DIBUAT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://cogniflip-demo.vercel.app", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],   # WAJIB include OPTIONS
    allow_headers=["*"],   # WAJIB allow Authorization header
)

# 3. KONFIGURASI KEAMANAN (Rate Limiting & Security Headers)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

ALLOWED_ORIGINS = ["https://cogniflip-demo.vercel.app", "http://localhost:3000"]

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.critical(f"Unhandled Exception at {request.url}: {exc}", exc_info=True)
    origin = request.headers.get("origin")
    headers = {}
    if origin in ALLOWED_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(status_code=500, content={"detail": "Internal server error"}, headers=headers)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Server"] = "CogniFlip-Shield"
    return response

# 4. MASUKKAN ROUTER
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(session.router, prefix="/api/v1/sessions", tags=["sessions"])
app.include_router(voice.router, prefix="/api/v1/voice")