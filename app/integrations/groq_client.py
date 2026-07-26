from groq import AsyncGroq
from typing import AsyncGenerator

class GroqClient:
    def __init__(self, api_key: str):
        self.client = AsyncGroq(api_key=api_key)

    async def chat_completion(
        self, 
        model: str, 
        messages: list, 
        temperature: float = 0.7, 
        response_format: dict = None
    ) -> str:
        kwargs = {"model": model, "messages": messages, "temperature": temperature}
        if response_format:
            kwargs["response_format"] = response_format

        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    async def stream_chat_completion(self, model: str, messages: list) -> AsyncGenerator[str, None]:
        stream = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=150,
            stream=True
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content

    # --- TAMBAHKAN FUNGSI INI ---
    async def transcribe_audio(self, audio_bytes: bytes, filename: str) -> str:
        """
        Mengirim file audio ke Groq Whisper API secara asinkron.
        """
        try:
            # Mengirim tuple (nama_file, bytes) langsung ke Groq API
            response = await self.client.audio.transcriptions.create(
                file=(filename, audio_bytes),
                model="whisper-large-v3", # Model whisper tercepat saat ini
                response_format="text"    # Kita minta format teks langsung
            )
            return response
        except Exception as e:
            raise RuntimeError("Groq transcription failed") from e