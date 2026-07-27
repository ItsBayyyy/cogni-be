from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Response, Request
from pydantic import BaseModel, Field, field_validator
from app.core.config import get_settings, Settings
from app.integrations.groq_client import GroqClient
from app.integrations.edge_tts_client import EdgeTTSClient
from app.services.voice_service import VoiceService
from app.api.dependencies import get_current_user
from app.core.audio_validation import (
    ALLOWED_AUDIO_TYPES,
    has_valid_audio_signature,
    normalize_audio_type,
)
from app.core.security import limiter
import logging
import traceback

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])

# --- Schema ---
class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Text cannot be blank")
        return value

MAX_AUDIO_BYTES = 10 * 1024 * 1024

# --- Dependencies ---
def get_voice_service(settings: Settings = Depends(get_settings)) -> VoiceService:
    groq = GroqClient(api_key=settings.GROQ_API_KEY)
    tts = EdgeTTSClient(voice=settings.EDGE_TTS_VOICE)
    return VoiceService(groq_client=groq, tts_client=tts)

# --- Endpoints ---

@router.post("/transcribe", summary="Speech-to-Text (Groq Whisper)")
@limiter.limit("10/minute")
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(..., description="Upload a .wav, .mp3, or .m4a file"),
    service: VoiceService = Depends(get_voice_service),
    current_user_id: str = Depends(get_current_user)
):
    media_type = normalize_audio_type(file.content_type)
    if media_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported audio type")

    audio_bytes = await file.read(MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file is too large")
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty")
    if not has_valid_audio_signature(audio_bytes, media_type):
        raise HTTPException(status_code=415, detail="Audio content does not match its type")
    
    try:
        # Menjalankan proses transkripsi
        text = await service.process_audio_input(audio_bytes, file.filename)
        return {"text": text}
    except Exception as e:
        logger.error(f"Transcribe Error: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal processing error. Please try again.")

@router.post("/speak", summary="Text-to-Speech (Edge TTS)")
@limiter.limit("20/minute")
async def generate_speech(
    request: Request,
    payload: TTSRequest,
    service: VoiceService = Depends(get_voice_service),
    current_user_id: str = Depends(get_current_user)
):
    """
    Mengubah teks menjadi file audio (MP3).
    """
    try:
        audio_bytes = await service.generate_audio_output(payload.text)
        
        # Mengembalikan file audio langsung sebagai response, bukan JSON
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"TTS Error: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal processing error. Please try again.")
