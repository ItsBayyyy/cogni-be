ALLOWED_AUDIO_TYPES = {
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "video/webm",
}


def normalize_audio_type(content_type: str | None) -> str:
    """Remove optional MIME parameters such as ``codecs=opus``."""
    return (content_type or "").split(";", 1)[0].strip().lower()


def has_valid_audio_signature(data: bytes, media_type: str) -> bool:
    """Reject files whose declared audio container does not match its bytes."""
    if media_type in {"audio/webm", "video/webm"}:
        return data.startswith(b"\x1a\x45\xdf\xa3")
    if media_type == "audio/ogg":
        return data.startswith(b"OggS")
    if media_type == "audio/wav":
        return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WAVE"
    if media_type == "audio/mp4":
        return len(data) >= 12 and data[4:8] == b"ftyp"
    if media_type == "audio/mpeg":
        return data.startswith(b"ID3") or (
            len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0
        )
    return False
