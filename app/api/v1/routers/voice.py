from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Response
from pydantic import BaseModel
from app.core.config import get_settings, Settings
from app.integrations.groq_client import GroqClient
from app.integrations.edge_tts_client import EdgeTTSClient
from app.services.voice_service import VoiceService
from app.api.dependencies import get_current_user
import logging
import traceback

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])

# --- Schema ---
class TTSRequest(BaseModel):
    text: str

# --- Dependencies ---
def get_voice_service(settings: Settings = Depends(get_settings)) -> VoiceService:
    groq = GroqClient(api_key=settings.GROQ_API_KEY)
    tts = EdgeTTSClient(voice=settings.EDGE_TTS_VOICE)
    return VoiceService(groq_client=groq, tts_client=tts)

# --- Endpoints ---

@router.post("/transcribe", summary="Speech-to-Text (Groq Whisper)")
async def transcribe_audio(
    file: UploadFile = File(..., description="Upload a .wav, .mp3, or .m4a file"),
    service: VoiceService = Depends(get_voice_service),
    current_user_id: str = Depends(get_current_user)
):
    audio_bytes = await file.read()
    
    try:
        # Menjalankan proses transkripsi
        text = await service.process_audio_input(audio_bytes, file.filename)
        return {"text": text}
    except Exception as e:
        logger.error(f"Transcribe Error: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal processing error. Please try again.")

@router.post("/speak", summary="Text-to-Speech (Edge TTS)")
async def generate_speech(
    request: TTSRequest,
    service: VoiceService = Depends(get_voice_service),
    current_user_id: str = Depends(get_current_user)
):
    """
    Mengubah teks menjadi file audio (MP3).
    """
    try:
        audio_bytes = await service.generate_audio_output(request.text)
        
        # Mengembalikan file audio langsung sebagai response, bukan JSON
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"TTS Error: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal processing error. Please try again.")
