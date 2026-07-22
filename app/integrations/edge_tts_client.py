import logging

import edge_tts


class EdgeTTSClient:
    def __init__(self, voice: str = "en-US-AvaMultilingualNeural"):
        self.voice = voice

    async def text_to_speech(self, text: str) -> bytes:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Text tidak boleh kosong")

        communicate = edge_tts.Communicate(clean_text, self.voice)
        audio_chunks: list[bytes] = []

        try:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])

            if not audio_chunks:
                raise RuntimeError("Edge TTS tidak menghasilkan audio")

            return b"".join(audio_chunks)
        except Exception as e:
            logging.error(f"Edge TTS gagal: {e}")
            raise
