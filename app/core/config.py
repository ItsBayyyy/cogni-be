from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "CogniFlip"
    VERSION: str = "1.0.0"

    GROQ_API_KEY: str
    EDGE_TTS_VOICE: str = "en-US-AvaMultilingualNeural"
    
    DATABASE_URL: str
    JWT_SECRET: str = Field(min_length=43)
    JWT_ISSUER: str = "cogniflip-api"
    JWT_AUDIENCE: str = "cogniflip-web"
    ACCESS_TOKEN_MINUTES: int = Field(default=15, ge=5, le=60)
    OTP_PEPPER: str = Field(min_length=32)
    FALLBACK_ENCRYPTION_KEY: str = ""
    REDIS_URL: str = ""
    TRUSTED_PROXY_IPS: str = ""
    CORS_ORIGINS: str = "https://cogniflip-demo.vercel.app,http://localhost:3000"
    DEMO_LOGIN_ENABLED: bool = False
    
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = "CogniFlip <onboarding@resend.dev>"
    
    RESEND_API_KEY: str = ""
    BREVO_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

def get_settings() -> Settings:
    return Settings()
