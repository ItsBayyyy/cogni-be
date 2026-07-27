import pytest
import os
import sqlite3
from contextlib import closing
from unittest.mock import AsyncMock
from cryptography.fernet import Fernet
from app.services.transcript_service import TranscriptService
from app.core.postgres_client import PostgresClient

@pytest.mark.asyncio
async def test_postgres_fallback_to_sqlite():
    mock_db = AsyncMock(spec=PostgresClient)
    mock_db.insert.side_effect = Exception("Simulasi PostgreSQL Timeout/Down!")
    mock_db.select_by_eq_ordered.return_value = []

    service = TranscriptService(
        db=mock_db,
        fallback_encryption_key=Fernet.generate_key().decode("utf-8"),
    )
    
    test_db_path = "test_fallback.db"
    service.fallback_db = test_db_path

    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    await TranscriptService.init_fallback_db(test_db_path)

    session_id = "chaos-test-session-123"

    print("\n--- Memulai Tes Penulisan (Harap lihat log Retry) ---")
    result = await service.add_message(session_id, "user", "Tes sistem ketahanan!")

    assert result.content == "Tes sistem ketahanan!"
    
    assert mock_db.insert.call_count == 4

    assert os.path.exists(test_db_path)
    with closing(sqlite3.connect(test_db_path)) as db:
        ciphertext = db.execute(
            """
            SELECT payload_ciphertext
            FROM offline_transcripts_encrypted
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()[0]
    assert b"Tes sistem ketahanan!" not in bytes(ciphertext)

    print("\n--- Memulai Tes Pembacaan dari SQLite ---")
    transcript = await service.get_transcript(session_id)
    
    assert len(transcript.messages) == 1
    assert transcript.messages[0].content == "Tes sistem ketahanan!"
    assert transcript.messages[0].role == "user"

    print("✅ TEST PASSED: Fallback ACID SQLite bekerja sempurna!")

    if os.path.exists(test_db_path):
        os.remove(test_db_path)
