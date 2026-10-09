"""Short-lived claims that hold a marked image until its ID is on chain.

The old ``/mark`` handed back the marked PNG before registration. Because the
hidden ID is readable from that PNG by anyone (the decoder is public), an
observer could read the ID and register it first, squatting the record.

A claim closes that window: ``/mark`` keeps the marked image server-side and
returns only an opaque token. The image is revealed when the record lands:

* ``/register`` with a matching claim returns the image and burns the token, or
* ``/claim`` returns it only once the ID is actually present in the registry.

Either way the marked bytes never leave the server before the ID is claimed on
chain, so there is nothing to front-run. Claims are in-memory, single-use and
expire; a restart simply drops pending marks, which the client re-creates.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

DEFAULT_TTL = 900        # 15 minutes: comfortably longer than a passkey prompt
DEFAULT_MAX = 2000       # bound worst-case memory when the service is busy


@dataclass(frozen=True)
class Claim:
    token: str
    watermark_id: str
    fingerprint: str
    image_png_base64: str
    ip: str
    created: float


class ClaimStore:
    """Thread-safe, bounded, TTL store keyed by an unguessable token."""

    def __init__(self, ttl: float = DEFAULT_TTL, max_items: int = DEFAULT_MAX):
        self.ttl = float(ttl)
        self.max_items = max(1, int(max_items))
        self._by_token: dict[str, Claim] = {}
        self._by_id: dict[str, str] = {}  # watermark_id (lowercase) -> token
        self._lock = threading.Lock()

    def _expired(self, c: Claim, now: float) -> bool:
        return now - c.created > self.ttl

    def _drop(self, token: str) -> None:
        c = self._by_token.pop(token, None)
        if c is not None and self._by_id.get(c.watermark_id.lower()) == token:
            self._by_id.pop(c.watermark_id.lower(), None)

    def _sweep(self, now: float) -> None:
        for token in [t for t, c in self._by_token.items() if self._expired(c, now)]:
            self._drop(token)
        # Leave room for the claim about to be inserted, so the store never
        # exceeds max_items after put().
        target = self.max_items - 1
        if len(self._by_token) > target:
            for token in sorted(self._by_token, key=lambda t: self._by_token[t].created)[
                : len(self._by_token) - target
            ]:
                self._drop(token)

    def put(self, watermark_id: str, fingerprint: str, image_png_base64: str, ip: str = "") -> Claim:
        now = time.time()
        token = secrets.token_urlsafe(32)
        claim = Claim(token, watermark_id.lower(), fingerprint.lower().removeprefix("0x"),
                      image_png_base64, ip, now)
        with self._lock:
            self._sweep(now)
            # One outstanding claim per ID keeps the map small and unambiguous.
            old = self._by_id.get(claim.watermark_id)
            if old:
                self._drop(old)
            self._by_token[token] = claim
            self._by_id[claim.watermark_id] = token
        return claim

    def get(self, token: str) -> Claim | None:
        """Look up a live claim without consuming it."""
        if not token:
            return None
        now = time.time()
        with self._lock:
            c = self._by_token.get(token)
            if c is None:
                return None
            if self._expired(c, now):
                self._drop(token)
                return None
            return c

    def take(self, token: str, watermark_id: str, fingerprint: str) -> Claim | None:
        """Consume a claim if it matches the ID and fingerprint being registered."""
        if not token:
            return None
        now = time.time()
        want_id = (watermark_id or "").lower()
        want_fp = (fingerprint or "").lower().removeprefix("0x")
        with self._lock:
            c = self._by_token.get(token)
            if c is None or self._expired(c, now):
                if c is not None:
                    self._drop(token)
                return None
            if c.watermark_id != want_id or c.fingerprint != want_fp:
                return None
            self._drop(token)
            return c

    def take_by_id(self, watermark_id: str) -> Claim | None:
        """Consume the claim for an ID (used when the record is already on chain)."""
        with self._lock:
            token = self._by_id.get((watermark_id or "").lower())
            if token is None:
                return None
            c = self._by_token.get(token)
            if c is None or self._expired(c, time.time()):
                if c is not None:
                    self._drop(token)
                return None
            self._drop(token)
            return c

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_token)
