import asyncpg
import logging
import uuid as uuid_mod
from datetime import datetime, date
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

def _normalize_row(row) -> dict:
    """Convert PostgreSQL native types (UUID, datetime) to strings
    so downstream code stays compatible with the old Supabase client."""
    result = {}
    for key, value in dict(row).items():
        if isinstance(value, uuid_mod.UUID):
            result[key] = str(value)
        elif isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result

_global_pool = None

ALLOWED_TABLES = {"users", "sessions", "transcripts", "otps"}
ALLOWED_COLUMNS = {
    "id", "email", "session_id", "user_id", "created_at",
    "otp_code", "expires_at", "role", "content",
}

def _validate_identifier(value: str, allowed: set, kind: str = "identifier"):
    if value not in allowed:
        raise ValueError(f"Disallowed {kind}: {value}")

class PostgresClient:
    def __init__(self, url: str):
        self.url = url
        self.pool = None

    async def connect(self):
        global _global_pool
        if _global_pool is None:
            _global_pool = await asyncpg.create_pool(self.url)
        self.pool = _global_pool

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def insert(self, table: str, data: dict) -> Optional[dict]:
        _validate_identifier(table, ALLOWED_TABLES, "table")
        if not self.pool:
            await self.connect()
            
        columns = ", ".join(data.keys())
        placeholders = ", ".join(f"${i+1}" for i in range(len(data)))
        values = list(data.values())
        
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING *"
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, *values)
                return _normalize_row(row) if row else None
        except Exception as e:
            logger.error(f"Error inserting into {table}: {e}")
            raise

    async def select_by_eq(self, table: str, column: str, value: Any) -> List[dict]:
        _validate_identifier(table, ALLOWED_TABLES, "table")
        _validate_identifier(column, ALLOWED_COLUMNS, "column")
        if not self.pool:
            await self.connect()
            
        query = f"SELECT * FROM {table} WHERE {column} = $1"
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, value)
                return [_normalize_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Error selecting from {table}: {e}")
            raise

    async def select_by_eq_ordered(self, table: str, column: str, value: Any, order_col: str, asc: bool = True) -> List[dict]:
        _validate_identifier(table, ALLOWED_TABLES, "table")
        _validate_identifier(column, ALLOWED_COLUMNS, "column")
        _validate_identifier(order_col, ALLOWED_COLUMNS, "column")
        if not self.pool:
            await self.connect()
            
        order_dir = "ASC" if asc else "DESC"
        query = f"SELECT * FROM {table} WHERE {column} = $1 ORDER BY {order_col} {order_dir}"
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, value)
                return [_normalize_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Error selecting from {table} ordered: {e}")
            raise

    async def fetchrow(self, query: str, *args):
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return _normalize_row(row) if row else None
            
    async def execute(self, query: str, *args):
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
