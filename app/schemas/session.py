from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Literal

PersonaType = Literal["friendly", "strict", "socratic", "comedian", "nain"]

class SessionStartRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=300, description="Topik yang dibicarakan.")
    persona: PersonaType = Field(default="friendly", description="Persona AI murid.")

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Topic must contain at least 3 non-whitespace characters")
        return value

class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    topic: str
    persona: PersonaType
    status: str
    created_at: datetime
