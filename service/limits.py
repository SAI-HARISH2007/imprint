"""Sliding-window rate limits, client-IP resolution and a concurrency cap.

Kept separate from the HTTP layer so the rules are testable without FastAPI.
"""
import os
import threading
import time
from collections import deque

MAX_KEY_LEN = 64
MAX_KEYS = 20_000


class RateLimited(Exception):
    """Raised when a caller has run out of quota. Maps to HTTP 429."""

    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.message = message
        self.retry_after = max(1, int(retry_after))


class Busy(Exception):
    """Raised when too much work is already in flight. Maps to HTTP 503."""


class Limiter:
    """A per-key sliding window. check() only looks, record() spends."""

    def __init__(self, limit: int, window: float, name: str = ""):
        self.limit = max(0, int(limit))
        self.window = float(window)
        self.name = name
        self._q: dict[str, deque] = {}
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, q: deque, now: float) -> None:
        while q and now - q[0] > self.window:
            q.popleft()
        self._seen[key] = now

    def _evict(self, now: float) -> None:
        if len(self._q) <= MAX_KEYS:
            return
        # Drop the keys that have not been used for a full window; if that is not
        # enough, drop the oldest-touched keys outright so the dict stays bounded.
        for k in [k for k, t in self._seen.items() if now - t > self.window]:
            self._q.pop(k, None)
            self._seen.pop(k, None)
            if len(self._q) <= MAX_KEYS:
                return
        for k in sorted(self._seen, key=self._seen.get)[: len(self._q) - MAX_KEYS]:
            self._q.pop(k, None)
            self._seen.pop(k, None)

    def _retry_after(self, q: deque, now: float) -> int:
        if not q:
            return 0
        return int(q[0] + self.window - now) + 1

    def check(self, key: str) -> None:
        """Raise RateLimited if `key` has no quota left. Records nothing."""
        if self.limit <= 0:
            return
        now = time.time()
        with self._lock:
            q = self._q.get(key)
            if q is None:
                return
            self._prune(key, q, now)
            if len(q) >= self.limit:
                raise RateLimited("", self._retry_after(q, now))

    def record(self, key: str) -> None:
        """Spend one unit of quota for `key`."""
        if self.limit <= 0:
            return
        now = time.time()
        with self._lock:
            self._evict(now)
            q = self._q.setdefault(key, deque())
            self._prune(key, q, now)
            q.append(now)

    def take(self, key: str) -> None:
        """check() + record() as one atomic step."""
        if self.limit <= 0:
            return
        now = time.time()
        with self._lock:
            self._evict(now)
            q = self._q.get(key)
            if q is None:
                q = self._q.setdefault(key, deque())
            self._prune(key, q, now)
            if len(q) >= self.limit:
                raise RateLimited("", self._retry_after(q, now))
            q.append(now)

    def used(self, key: str) -> int:
        with self._lock:
            q = self._q.get(key)
            if not q:
                return 0
            self._prune(key, q, time.time())
            return len(q)


class ConcurrencyCap:
    """Bounds how many pieces of expensive work run at once."""

    def __init__(self, limit: int):
        self._sem = threading.BoundedSemaphore(max(1, int(limit)))
        self._limit = max(1, int(limit))
        self._active = 0
        self._lock = threading.Lock()

    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    class _Slot:
        def __init__(self, owner: "ConcurrencyCap"):
            self.owner = owner

        def __enter__(self):
            if not self.owner._sem.acquire(timeout=0.05):
                raise Busy(f"the service is at its concurrency limit of {self.owner._limit}")
            with self.owner._lock:
                self.owner._active += 1
            return self

        def __exit__(self, *exc):
            with self.owner._lock:
                self.owner._active -= 1
            self.owner._sem.release()
            return False

    def slot(self) -> "ConcurrencyCap._Slot":
        return ConcurrencyCap._Slot(self)


def _split_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [p.strip() for p in raw.split(",") if p.strip()]


def trusted_proxies() -> list[str]:
    """Who may speak for the client in X-Forwarded-For. Default: anyone (the
    platform proxy). Set to 127.0.0.1,::1 when the app is exposed directly so
    that client-supplied headers are ignored."""
    return _split_env("IMPRINT_TRUSTED_PROXIES", "*")


def xff_hops() -> int:
    """How many proxies append to X-Forwarded-For in front of us (CDN + LB = 2)."""
    try:
        return max(1, int(os.getenv("IMPRINT_XFF_HOPS", "1")))
    except ValueError:
        return 1


def _in_trusted(peer: str, trusted: list[str]) -> bool:
    if "*" in trusted:
        return True
    return peer in trusted


def _clean(value: str) -> str | None:
    """Reject anything that does not look like an IP we would be happy logging."""
    v = value.strip()
    if not v or len(v) > 45 or any(c.isspace() or c in ",\r\n" for c in v):
        return None
    return v


def client_ip(peer: str | None, forwarded_for: str | None) -> str:
    """The client address to rate limit.

    X-Forwarded-For is only consulted when the TCP peer is a configured trusted
    proxy, and we take the hop our proxy appended (rightmost, minus the extra
    hops we are told about) rather than the leftmost value, which the client
    controls and can therefore vary at will to escape a per-IP limit.
    """
    peer_clean = _clean(peer or "") or "unknown"
    if not forwarded_for or not _in_trusted(peer_clean, trusted_proxies()):
        return peer_clean
    hops = [h for h in (_clean(p) for p in forwarded_for.split(",")) if h]
    if not hops:
        return peer_clean
    idx = len(hops) - xff_hops()
    if idx < 0:
        idx = 0
    return hops[idx]
