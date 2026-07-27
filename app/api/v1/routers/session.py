import asyncio
import json
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from app.core.config import get_settings, Settings
from app.core.postgres_client import PostgresClient
from app.integrations.groq_client import GroqClient
from app.services.session_service import SessionService
from app.services.transcript_service import TranscriptService
from app.agents.student_agent import StudentAgent
from app.agents.professor_agent import ProfessorAgent
from app.schemas.session import SessionStartRequest, SessionResponse
from app.schemas.transcript import MessageRequest, TranscriptResponse
from app.schemas.evaluation import EvaluationResponse
from app.api.dependencies import get_current_user, get_turn_guard
from app.core.security import limiter
from app.core.speech_text import normalize_assistant_speech
from app.core.turn_guard import TurnGuard

logger = logging.getLogger(__name__)
router = APIRouter(tags=["session"])

# --- Dependencies ---
def get_db(settings: Settings = Depends(get_settings)) -> PostgresClient:
    return PostgresClient(url=settings.DATABASE_URL)

def get_groq(settings: Settings = Depends(get_settings)) -> GroqClient:
    return GroqClient(api_key=settings.GROQ_API_KEY)

def get_session_service(db: PostgresClient = Depends(get_db)) -> SessionService:
    return SessionService(db=db)

def get_transcript_service(
    db: PostgresClient = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TranscriptService:
    return TranscriptService(
        db=db,
        fallback_encryption_key=settings.FALLBACK_ENCRYPTION_KEY,
    )

def get_student_agent(groq: GroqClient = Depends(get_groq)) -> StudentAgent:
    return StudentAgent(groq_client=groq)

def get_professor_agent(groq: GroqClient = Depends(get_groq)) -> ProfessorAgent:
    return ProfessorAgent(groq_client=groq)

# --- Endpoints ---

@router.post("/start", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/hour")
async def start_session(
    request: Request,
    payload: SessionStartRequest,
    service: SessionService = Depends(get_session_service),
    current_user_id: str = Depends(get_current_user) # Wajib bawa token JWT
):
    return await service.create_session(user_id=current_user_id, topic=payload.topic, persona=payload.persona)

@router.get("/", response_model=List[SessionResponse])
async def get_all_sessions(
    service: SessionService = Depends(get_session_service),
    current_user_id: str = Depends(get_current_user)
):
    """Mengambil daftar riwayat sesi untuk halaman Reports berdasarkan User yang login."""
    return await service.get_user_sessions(user_id=current_user_id)


@router.post("/{id}/message")
@limiter.limit("20/minute")
async def add_message_stream(
    id: str,
    request_data: MessageRequest,
    request: Request,
    session_service: SessionService = Depends(get_session_service),
    transcript_service: TranscriptService = Depends(get_transcript_service),
    student_agent: StudentAgent = Depends(get_student_agent),
    turn_guard: TurnGuard = Depends(get_turn_guard),
    current_user_id: str = Depends(get_current_user) # Keamanan: Cek token
):
    # Dapatkan sesi sekaligus personanya
    session = await session_service.get_session(id)
    if not session or session.user_id != current_user_id:
        raise HTTPException(status_code=404, detail="Session not found or unauthorized")

    turn_token = await turn_guard.acquire(id, current_user_id)
    if not turn_token:
        raise HTTPException(status_code=409, detail="A turn is already in progress")

    try:
        transcript = await transcript_service.get_transcript(session_id=id)
        await transcript_service.add_message(id, "user", request_data.content)
    except Exception:
        await turn_guard.release(id, current_user_id, turn_token)
        raise

    async def sse_generator():
        ai_full_text = ""
        try:
            # Mengirimkan persona dari database sesi ke Agent!
            async for chunk in student_agent.generate_stream(transcript.messages, request_data.content, persona=session.persona, topic=session.topic):
                if await request.is_disconnected():
                    logger.warning(f"Client disconnected for session {id}. Halting Groq LLM Stream.")
                    break
                
                ai_full_text += chunk
                yield f"data: {json.dumps({'content': chunk})}\n\n"

            if not await request.is_disconnected():
                yield "data: [DONE]\n\n"

        except asyncio.CancelledError:
            logger.warning(f"Stream generation cancelled by client disconnect for session {id}.")
            raise 

        finally:
            try:
                if ai_full_text:
                    stored_text = normalize_assistant_speech(ai_full_text)
                    await transcript_service.add_message(id, "student_agent", stored_text)
            finally:
                await turn_guard.release(id, current_user_id, turn_token)

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@router.post("/{id}/evaluate", response_model=EvaluationResponse)
@limiter.limit("5/minute")
async def evaluate_session(
    id: str,
    request: Request,
    session_service: SessionService = Depends(get_session_service),
    transcript_service: TranscriptService = Depends(get_transcript_service),
    professor_agent: ProfessorAgent = Depends(get_professor_agent),
    current_user_id: str = Depends(get_current_user)
):
    session = await session_service.get_session(id)
    if not session or session.user_id != current_user_id:
        raise HTTPException(status_code=404, detail="Session not found or unauthorized")

    transcript = await transcript_service.get_transcript(session_id=id)
    if len(transcript.messages) < 2:
        raise HTTPException(status_code=400, detail="Insufficient messages")

    eval_data = await professor_agent.evaluate(transcript.messages)
    return EvaluationResponse(**eval_data)


@router.get("/{id}/transcript", response_model=TranscriptResponse)
async def get_session_transcript(
    id: str,
    session_service: SessionService = Depends(get_session_service),
    transcript_service: TranscriptService = Depends(get_transcript_service),
    current_user_id: str = Depends(get_current_user)
):
    session = await session_service.get_session(id)
    if not session or session.user_id != current_user_id:
        raise HTTPException(status_code=404, detail="Session not found or unauthorized")
        
    return await transcript_service.get_transcript(session_id=id)
