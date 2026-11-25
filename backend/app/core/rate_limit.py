"""In-memory sliding-window login rate limiter and temporary lockout guard."""

from collections import deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Deque, Dict, Optional

from app.core.config import settings


class LoginRateLimiter:
    """
    Tracks failed login attempts per client IP and per normalized email.
    Triggers a temporary lockout once `max_attempts` failures occur inside
    the rolling `window_minutes` window.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._attempts: Dict[str, Deque[datetime]] = {}
        self._locked_until: Dict[str, datetime] = {}

    def _keys(self, ip: str, email: str) -> tuple[str, str]:
        return f"ip:{ip or 'unknown'}", f"email:{(email or '').strip().lower()}"

    def _prune(self, key: str, now: datetime, window: timedelta) -> Deque[datetime]:
        q = self._attempts.setdefault(key, deque())
        cutoff = now - window
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def check_blocked(self, ip: str, email: str) -> Optional[int]:
        """Return Retry-After seconds if either IP or email is locked out, else None."""
        now = datetime.now(timezone.utc)
        with self._lock:
            remaining_secs = 0
            for key in self._keys(ip, email):
                until = self._locked_until.get(key)
                if until:
                    if until > now:
                        remaining_secs = max(remaining_secs, int((until - now).total_seconds()) + 1)
                    else:
                        self._locked_until.pop(key, None)
            return remaining_secs if remaining_secs > 0 else None

    def record_failure(self, ip: str, email: str) -> Optional[int]:
        """Record a failed login attempt; returns lockout seconds if threshold reached."""
        now = datetime.now(timezone.utc)
        window = timedelta(minutes=settings.LOGIN_WINDOW_MINUTES)
        lockout = timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
        max_attempts = max(1, settings.LOGIN_MAX_ATTEMPTS)

        with self._lock:
            lock_secs: Optional[int] = None
            for key in self._keys(ip, email):
                q = self._prune(key, now, window)
                q.append(now)
                if len(q) >= max_attempts:
                    self._locked_until[key] = now + lockout
                    q.clear()
                    lock_secs = int(lockout.total_seconds())
            return lock_secs

    def record_success(self, ip: str, email: str) -> None:
        """Clear failure counters on successful login."""
        with self._lock:
            for key in self._keys(ip, email):
                self._attempts.pop(key, None)
                self._locked_until.pop(key, None)

    def reset(self) -> None:
        """Clear all state (used in tests)."""
        with self._lock:
            self._attempts.clear()
            self._locked_until.clear()


login_rate_limiter = LoginRateLimiter()
