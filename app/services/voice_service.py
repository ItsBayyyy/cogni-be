from app.integrations.groq_client import GroqClient
from app.integrations.edge_tts_client import EdgeTTSClient

class VoiceService:
    def __init__(self, groq_client: GroqClient, tts_client: EdgeTTSClient):
        self.groq_client = groq_client
        self.tts_client = tts_client

    async def process_audio_input(self, audio_bytes: bytes, filename: str = "upload.wav") -> str:
        text = await self.groq_client.transcribe_audio(audio_bytes, filename)
        return text

    async def generate_audio_output(self, text: str) -> bytes:
        audio_bytes = await self.tts_client.text_to_speech(text)
        return audio_bytes
