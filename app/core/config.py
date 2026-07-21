from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "CogniFlip"
    VERSION: str = "1.0.0"

    GROQ_API_KEY: str
    EDGE_TTS_VOICE: str = "en-US-AvaMultilingualNeural"
    
    DATABASE_URL: str
    JWT_SECRET: str = "supersecretjwtkey123"

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

def get_settings() -> Settings:
    return Settings()
