import json
from app.integrations.groq_client import GroqClient
from app.schemas.transcript import MessageResponse

class ProfessorAgent:
    def __init__(self, groq_client: GroqClient):
        self.client = groq_client
        self.model = "llama-3.3-70b-versatile"
        # Prompt disesuaikan mutlak dengan UI Evaluation
        self.system_prompt = """You are a highly analytical communication coach evaluating a conversation transcript between a USER and COGNIFLIP AI.
When writing highlights or descriptions, DO NOT use internal role tags like "STUDENT_AGENT" or "USER" verbatim. Instead, use natural language (e.g., "you", "the AI", "CogniFlip"). Address the USER directly ("You did X well").
You MUST output your response strictly as a JSON object matching this exact schema:
{
  "overall_score": <number 0-100>,
  "highlights": [
    {"type": "positive", "title": "Strong opening", "description": "..."},
    {"type": "negative", "title": "Tighten the middle", "description": "..."}
  ],
  "breakdown": {
    "clarity": <number 0-100>,
    "depth": <number 0-100>,
    "pacing": <number 0-100>,
    "charisma": <number 0-100>
  }
}"""

    async def evaluate(self, transcript: list[MessageResponse]) -> dict:
        def get_speaker_name(role: str) -> str:
            return "USER" if role == "user" else "COGNIFLIP AI"
            
        transcript_text = "\n".join([f"[{msg.created_at}] {get_speaker_name(msg.role)}: {msg.content}" for msg in transcript])
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Evaluate this transcript:\n\n{transcript_text}"}
        ]

        response_text = await self.client.chat_completion(
            model=self.model,
            messages=messages,
            temperature=0.0, 
            response_format={"type": "json_object"}
        )
        return json.loads(response_text)