import re


_LAUGHTER_DIRECTIONS = re.compile(
    r"(?:\*{1,2}\s*(?:laughs?|chuckles?|giggles?)\s*\*{1,2}"
    r"|\[\s*(?:laughs?|chuckles?|giggles?)\s*\]"
    r"|\(\s*(?:laughs?|chuckles?|giggles?)\s*\))",
    re.IGNORECASE,
)


def normalize_assistant_speech(text: str) -> str:
    normalized = _LAUGHTER_DIRECTIONS.sub("Ha—", text)
    normalized = re.sub(r"[ \t]+([,.!?])", r"\1", normalized)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    return normalized.strip()
