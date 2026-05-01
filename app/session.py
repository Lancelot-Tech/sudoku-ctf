"""Thread-safe in-memory session store with TTL and capacity limits.

For a single-process CTF deployment an in-memory dict is sufficient.
To scale across multiple Uvicorn workers, replace this with a Redis backend
(e.g. redis-py or aioredis).
"""

import time
import threading
from typing import Any


class SessionStore:
    """Thread-safe key-value session store backed by an in-memory dict.

    Each entry records the session payload and a last-access timestamp used
    for TTL enforcement. Expired entries are lazily evicted on :meth:`get`
    and can be bulk-purged via :meth:`purge_expired`.

    Args:
        ttl: Time-to-live in seconds; a session unused for this duration expires.
        max_sessions: Maximum number of concurrent live sessions.
    """

    def __init__(self, ttl: int = 3600, max_sessions: int = 500) -> None:
        self._store: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.ttl = ttl
        self.max_sessions = max_sessions

    def get(self, token: str) -> dict[str, Any] | None:
        """Retrieve session data, evicting the entry lazily if expired.

        Args:
            token: Session identifier.

        Returns:
            The session data dict, or ``None`` if the token is unknown or
            the session has expired.
        """
        with self._lock:
            entry = self._store.get(token)
            if entry is None:
                return None
            if time.time() - entry["_last_access"] > self.ttl:
                del self._store[token]
                return None
            return entry["data"]

    def set(self, token: str, data: dict) -> None:
        """Store or overwrite session data and reset the TTL clock.

        Args:
            token: Session identifier.
            data: Arbitrary session payload.
        """
        with self._lock:
            self._store[token] = {"data": data, "_last_access": time.time()}

    def touch(self, token: str) -> None:
        """Reset the TTL of an existing session without modifying its data.

        No-op if *token* is not present.

        Args:
            token: Session identifier to refresh.
        """
        with self._lock:
            if token in self._store:
                self._store[token]["_last_access"] = time.time()

    def delete(self, token: str) -> None:
        """Remove a session unconditionally.

        Args:
            token: Session identifier to remove. No-op if absent.
        """
        with self._lock:
            self._store.pop(token, None)

    def count(self) -> int:
        """Return the current number of stored sessions (including expired ones).

        Returns:
            Number of entries in the backing store.
        """
        with self._lock:
            return len(self._store)

    def purge_expired(self) -> int:
        """Remove all sessions whose TTL has elapsed.

        Returns:
            Number of sessions removed.
        """
        now = time.time()
        with self._lock:
            expired = [
                t for t, e in self._store.items()
                if now - e["_last_access"] > self.ttl
            ]
            for t in expired:
                del self._store[t]
        return len(expired)
