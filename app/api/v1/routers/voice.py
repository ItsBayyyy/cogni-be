from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Response
from pydantic import BaseModel
from app.core.config import get_settings, Settings
from app.integrations.groq_client import GroqClient
from app.integrations.edge_tts_client import EdgeTTSClient
from app.services.voice_service import VoiceService
import logging
import traceback # Tambahkan ini

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
    service: VoiceService = Depends(get_voice_service)
):
    audio_bytes = await file.read()
    
    try:
        # Menjalankan proses transkripsi
        text = await service.process_audio_input(audio_bytes, file.filename)
        return {"text": text}
    except Exception as e:
        # PENTING: Cetak detail error ke terminal agar kita tahu baris mana yang rusak
        print("===== DETAIL ERROR TRANSCRIBE =====")
        traceback.print_exc() 
        print("====================================")
        
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/speak", summary="Text-to-Speech (Edge TTS)")
async def generate_speech(
    request: TTSRequest,
    service: VoiceService = Depends(get_voice_service)
):
    """
    Mengubah teks menjadi file audio (MP3).
    """
    try:
        audio_bytes = await service.generate_audio_output(request.text)
        
        # Mengembalikan file audio langsung sebagai response, bukan JSON
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
