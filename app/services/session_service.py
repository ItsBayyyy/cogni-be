import uuid
from app.utils.time import get_current_timestamp
from app.core.postgres_client import PostgresClient
from app.schemas.session import SessionResponse

class SessionService:
    def __init__(self, db: PostgresClient):
        self.db = db

    async def create_session(self, user_id: str, topic: str, persona: str) -> SessionResponse:
        session_id = str(uuid.uuid4())
        
        session_data = {
            "session_id": session_id,
            "user_id": user_id, # Masukkan user_id
            "topic": topic,
            "persona": persona,
            "status": "active",
            "created_at": get_current_timestamp()
        }
        
        inserted_data = await self.db.insert(table="sessions", data=session_data)
        return SessionResponse(**inserted_data)

    async def get_session(self, session_id: str) -> SessionResponse | None:
        records = await self.db.select_by_eq(table="sessions", column="session_id", value=session_id)
        if not records:
            return None
        return SessionResponse(**records[0])

    # FUNGSI BARU UNTUK HALAMAN REPORTS
    async def get_user_sessions(self, user_id: str) -> list[SessionResponse]:
        records = await self.db.select_by_eq_ordered(
            table="sessions", 
            column="user_id", 
            value=user_id, 
            order_col="created_at", 
            asc=False # Urutkan dari yang paling baru
        )
        return [SessionResponse(**record) for record in records]