def format_chat_history(messages: list[dict]) -> str:
    return "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in messages])