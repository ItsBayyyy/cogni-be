from pydantic import BaseModel, Field
from typing import Literal, List

class MessageRequest(BaseModel):
    role: Literal['user', 'student_agent', 'professor_agent'] = Field(...)
    content: str = Field(..., description="The spoken or generated text.")

class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: str

class TranscriptResponse(BaseModel):
    session_id: str
    messages: List[MessageResponse]

class InteractionResponse(BaseModel):
    user_message: MessageResponse
    agent_message: MessageResponse