import uuid
import asyncio
import json
import logging
import aiosqlite
from app.utils.time import get_current_timestamp
from app.core.postgres_client import PostgresClient
from app.schemas.transcript import MessageResponse, TranscriptResponse

logger = logging.getLogger(__name__)

class TranscriptService:
    def __init__(self, db: PostgresClient):
        self.db = db
        self.fallback_db = "fallback.db"

    @classmethod
    async def init_fallback_db(cls, db_path: str = "fallback.db"):
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS offline_transcripts (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            await db.commit()
            logger.info("SQLite fallback database initialized with offline_transcripts table.")

    async def add_message(self, session_id: str, role: str, content: str) -> MessageResponse:
        message_data = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": get_current_timestamp()
        }

        max_retries = 3
        
        for attempt in range(max_retries + 1):
            try:
                inserted_data = await self.db.insert(table="transcripts", data=message_data)
                if not inserted_data:
                    return MessageResponse(**message_data)
                return MessageResponse(**inserted_data)

            except Exception as e:
                if attempt < max_retries:
                    delay = 2 ** attempt
                    logger.warning(f"[DB Write] Timeout/Error (Attempt {attempt + 1}/{max_retries}). Retrying in {delay}s... Error: {e}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"[DB Write] FATAL: All {max_retries} retries failed! Writing to SQLite fallback. Error: {e}")
                    await self._write_to_fallback_db(message_data)
                    return MessageResponse(**message_data)

    async def _write_to_fallback_db(self, data: dict):
        try:
            async with aiosqlite.connect(self.fallback_db) as db:
                await db.execute(
                    "INSERT INTO offline_transcripts (id, session_id, payload_json, timestamp) VALUES (?, ?, ?, ?)",
                    (data["id"], data["session_id"], json.dumps(data), data["created_at"])
                )
                await db.commit()
            logger.info(f"Payload ID {data['id']} safely written to {self.fallback_db}")
        except Exception as e:
            logger.critical(f"SRE CRITICAL ALERT: Failed to write to fallback SQLite! Data loss: {e}")

    async def get_transcript(self, session_id: str) -> TranscriptResponse:
        db_records = []
        fallback_records = []

        try:
            db_records = await self.db.select_by_eq_ordered(
                table="transcripts", 
                column="session_id", 
                value=session_id, 
                order_col="created_at",
                asc=True
            )
        except Exception as e:
            logger.error(f"[DB Read] Gagal mengambil transkrip dari database: {e}")

        try:
            async with aiosqlite.connect(self.fallback_db) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT payload_json FROM offline_transcripts WHERE session_id = ?",
                    (session_id,)
                ) as cursor:
                    async for row in cursor:
                        try:
                            fallback_records.append(json.loads(row["payload_json"]))
                        except json.JSONDecodeError:
                            logger.error("Corrupted JSON payload in SQLite fallback.")
        except Exception as e:
            logger.error(f"[Fallback Read] Gagal membaca fallback SQLite: {e}")

        combined_records = db_records + fallback_records

        combined_records.sort(key=lambda x: x.get("created_at", ""))

        seen_ids = set()
        unique_records = []
        for record in combined_records:
            if record.get("id") not in seen_ids:
                seen_ids.add(record.get("id"))
                unique_records.append(record)

        messages = [MessageResponse(**record) for record in unique_records]

        return TranscriptResponse(
            session_id=session_id,
            messages=messages
        )