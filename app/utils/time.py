from datetime import datetime, timezone

def get_current_timestamp() -> datetime:
    return datetime.now(timezone.utc)