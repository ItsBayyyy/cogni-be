from pydantic import BaseModel, Field
from typing import List, Literal

class Highlight(BaseModel):
    type: Literal['positive', 'negative'] = Field(..., description="positive untuk warna hijau, negative untuk merah")
    title: str = Field(..., description="Contoh: 'Strong opening' atau 'Tighten the middle'")
    description: str = Field(..., description="Penjelasan singkat")

class Breakdown(BaseModel):
    clarity: int = Field(..., ge=0, le=100)
    depth: int = Field(..., ge=0, le=100)
    pacing: int = Field(..., ge=0, le=100)
    charisma: int = Field(..., ge=0, le=100)

class EvaluationResponse(BaseModel):
    overall_score: int = Field(..., ge=0, le=100, description="Skor utama")
    highlights: List[Highlight]
    breakdown: Breakdown