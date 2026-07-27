import asyncio
import secrets
import time

from redis.asyncio import Redis


_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


class TurnGuard:
    """Cross-instance, expiring lock for one active turn per session."""

    def __init__(self, redis_url: str = "", ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self.redis = Redis.from_url(redis_url, decode_responses=True) if redis_url else None
        self._memory: dict[str, tuple[str, float]] = {}
        self._memory_lock = asyncio.Lock()

    @staticmethod
    def _key(session_id: str, user_id: str) -> str:
        return f"cogniflip:turn:{user_id}:{session_id}"

    async def acquire(self, session_id: str, user_id: str) -> str | None:
        key = self._key(session_id, user_id)
        token = secrets.token_urlsafe(24)
        if self.redis:
            acquired = await self.redis.set(
                key,
                token,
                nx=True,
                ex=self.ttl_seconds,
            )
            return token if acquired else None

        async with self._memory_lock:
            current = self._memory.get(key)
            now = time.monotonic()
            if current and current[1] > now:
                return None
            self._memory[key] = (token, now + self.ttl_seconds)
            return token

    async def release(self, session_id: str, user_id: str, token: str) -> None:
        key = self._key(session_id, user_id)
        if self.redis:
            await self.redis.eval(_RELEASE_SCRIPT, 1, key, token)
            return

        async with self._memory_lock:
            current = self._memory.get(key)
            if current and secrets.compare_digest(current[0], token):
                self._memory.pop(key, None)


_TURN_GUARDS: dict[str, TurnGuard] = {}


def get_shared_turn_guard(redis_url: str) -> TurnGuard:
    guard = _TURN_GUARDS.get(redis_url)
    if guard is None:
        guard = TurnGuard(redis_url=redis_url)
        _TURN_GUARDS[redis_url] = guard
    return guard
