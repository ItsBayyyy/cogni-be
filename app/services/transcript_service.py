import uuid
import asyncio
import json
import logging
import aiosqlite
from cryptography.fernet import Fernet, InvalidToken
from app.utils.time import get_current_timestamp
from app.core.postgres_client import PostgresClient
from app.schemas.transcript import MessageResponse, TranscriptResponse

logger = logging.getLogger(__name__)

class TranscriptService:
    def __init__(self, db: PostgresClient, fallback_encryption_key: str = ""):
        self.db = db
        self.fallback_db = "fallback.db"
        self._cipher = (
            Fernet(fallback_encryption_key.encode("utf-8"))
            if fallback_encryption_key
            else None
        )

    @classmethod
    async def init_fallback_db(cls, db_path: str = "fallback.db"):
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS offline_transcripts_encrypted (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    payload_ciphertext BLOB NOT NULL,
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

            except Exception:
                if attempt < max_retries:
                    delay = 2 ** attempt
                    logger.warning(
                        "[DB Write] attempt %s/%s failed; retrying in %ss",
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "[DB Write] all %s retries failed; using encrypted fallback",
                        max_retries,
                    )
                    await self._write_to_fallback_db(message_data)
                    return MessageResponse(**message_data)

    async def _write_to_fallback_db(self, data: dict):
        if not self._cipher:
            raise RuntimeError(
                "Encrypted fallback is disabled because FALLBACK_ENCRYPTION_KEY is not configured"
            )
        try:
            ciphertext = self._cipher.encrypt(
                json.dumps(data, default=str).encode("utf-8")
            )
            async with aiosqlite.connect(self.fallback_db) as db:
                await db.execute(
                    """
                    INSERT INTO offline_transcripts_encrypted
                        (id, session_id, payload_ciphertext, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (data["id"], data["session_id"], ciphertext, data["created_at"])
                )
                await db.commit()
            logger.info("Encrypted transcript payload written to fallback storage")
        except Exception:
            logger.critical("Failed to write encrypted fallback transcript")
            raise

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
        except Exception:
            logger.error("[DB Read] failed to retrieve transcript")

        if self._cipher:
            try:
                async with aiosqlite.connect(self.fallback_db) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute(
                        """
                        SELECT payload_ciphertext
                        FROM offline_transcripts_encrypted
                        WHERE session_id = ?
                        """,
                        (session_id,)
                    ) as cursor:
                        async for row in cursor:
                            try:
                                plaintext = self._cipher.decrypt(row["payload_ciphertext"])
                                fallback_records.append(json.loads(plaintext))
                            except (InvalidToken, json.JSONDecodeError):
                                logger.error("Invalid encrypted fallback transcript payload")
            except Exception:
                logger.error("Failed to read encrypted fallback transcript")

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
