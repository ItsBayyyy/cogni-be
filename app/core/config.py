from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "CogniFlip"
    VERSION: str = "1.0.0"

    GROQ_API_KEY: str
    EDGE_TTS_VOICE: str = "en-US-AvaMultilingualNeural"
    
    DATABASE_URL: str
    JWT_SECRET: str = "cogniflip_secret_jwt_key_32_characters_long_default"
    
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = "CogniFlip <no-reply@cogniflip.com>"

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

def get_settings() -> Settings:
    return Settings()
