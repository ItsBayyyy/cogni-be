from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import List
from datetime import datetime

class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=1, max_length=5000, description="The spoken text.")

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be blank")
        return value

class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime

class TranscriptResponse(BaseModel):
    session_id: str
    messages: List[MessageResponse]

class InteractionResponse(BaseModel):
    user_message: MessageResponse
    agent_message: MessageResponse
