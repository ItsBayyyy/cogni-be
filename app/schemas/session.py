from pydantic import BaseModel, Field
from typing import Literal

# Menggunakan 3 role asik untuk AI Murid
PersonaType = Literal['friendly', 'strict', 'socratic']

class SessionStartRequest(BaseModel):
    topic: str = Field(..., description="Topik yang dibicarakan.")
    persona: PersonaType = Field(default="friendly", description="Persona AI murid.")

class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    topic: str
    persona: str
    status: str
    created_at: str