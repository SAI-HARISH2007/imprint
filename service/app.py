"""HTTP face of Imprint. Run:  uvicorn app:app --port 8000"""
import collections
import datetime as dt
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import chain
import core
import stress
import verdict

MAX_BYTES = 30 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    core.payload_bits()  # load the model once at startup, not on the first request
    yield


app = FastAPI(title="Imprint", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


import logging
log = logging.getLogger("uvicorn.error")


def _read_upload(file: UploadFile) -> bytes:
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file is larger than 30 MB")
    log.info("upload %s: %d bytes, %s", file.filename, len(data), file.content_type)
    return data


def _rec(r: verdict.Record | None) -> dict | None:
    if r is None:
        return None
    return {
        "watermark_id": r.watermark_id,
        "fingerprint": r.fingerprint,
        "signer": r.signer,
        "timestamp": r.timestamp,
        "time": dt.datetime.fromtimestamp(r.timestamp, dt.timezone.utc).isoformat(),
        "block": r.block,
        "tx_hash": r.tx_hash or None,
        "tx_url": chain.explorer_tx(r.tx_hash) if r.tx_hash else None,
    }


@app.get("/health")
def health():
    return {"ok": True, "payload_bits": core.payload_bits()}


@app.get("/config")
def config():
    return {
        "chain_id": chain.CHAIN_ID, "registry": chain.REGISTRY,
        "registry_url": chain.explorer_address(chain.REGISTRY), "explorer": chain.EXPLORER,
        "thresholds": {"match": verdict.T_MATCH, "near": verdict.T_NEAR, "duplicate": verdict.T_DUP},
    }


@app.post("/mark")
def mark(file: UploadFile = File(...)):
    data = _read_upload(file)
    try:
        out = core.mark(data)
        log.info("mark %dx%d strength=%s self_test=%s", out["width"], out["height"], out["strength"], out["self_test"])
        return out
    except core.BadImage as e:
        raise HTTPException(400, str(e))


@app.post("/check")
def check(file: UploadFile = File(...)):
    """Raw read: the hidden ID (if any) and the fingerprint, with no registry lookup."""
    data = _read_upload(file)
    try:
        return core.read(data)
    except core.BadImage as e:
        raise HTTPException(400, str(e))


@app.get("/challenge")
def challenge(watermark_id: str, fingerprint: str):
    return {"challenge": chain.challenge_for(watermark_id, fingerprint)}


class Assertion(BaseModel):
    r: str
    s: str
    challengeIndex: int
    typeIndex: int
    authenticatorData: str
    clientDataJSON: str


class RegisterBody(BaseModel):
    watermark_id: str
    fingerprint: str
    auth: Assertion
    qx: str
    qy: str


# Protect the gas-paying wallet: a few registrations per visitor per hour, and a daily cap overall.
PER_IP_PER_HOUR = int(os.getenv("IMPRINT_PER_IP_HOUR", "6"))
GLOBAL_PER_DAY = int(os.getenv("IMPRINT_GLOBAL_DAY", "400"))
_hits: dict[str, collections.deque] = collections.defaultdict(collections.deque)
_all_hits: collections.deque = collections.deque()


def _rate_limit(ip: str) -> None:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    while _all_hits and now - _all_hits[0] > 86400:
        _all_hits.popleft()
    if len(q) >= PER_IP_PER_HOUR:
        raise HTTPException(429, "Too many registrations from this connection. Try again later.")
    if len(_all_hits) >= GLOBAL_PER_DAY:
        raise HTTPException(429, "The demo has reached its daily registration limit.")
    q.append(now)
    _all_hits.append(now)


@app.post("/register")
def register(body: RegisterBody, request: Request):
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    # Squatting guard: refuse an image that looks like an earlier registration by someone else.
    # Re-registering your own image with your own passkey is allowed.
    # (Checked before the rate limit so a refused duplicate does not use up the visitor's quota.)
    me = chain.passkey_signer(body.qx, body.qy).lower()
    others = [r for r in chain.all_records() if r.signer.lower() != me]
    lookalike = verdict.find_near_duplicate(body.fingerprint, others)
    if lookalike:
        rec, d = lookalike
        chain.tx_hash_for(rec)
        raise HTTPException(409, {
            "error": "near_duplicate",
            "message": "This image looks like one that was already registered by someone else.",
            "distance": d, "earlier": _rec(rec),
        })
    _rate_limit(ip)
    try:
        res = chain.register_passkey(body.watermark_id, body.fingerprint, body.auth.model_dump(), body.qx, body.qy)
    except chain.RelayError as e:
        raise HTTPException(400, str(e))
    chain._tx_cache[body.watermark_id.lower()] = res["tx_hash"]
    chain._records.pop(body.watermark_id.lower(), None)
    rec = chain.lookup(body.watermark_id)
    chain.refresh_index()
    return {**res, "record": _rec(rec)}


@app.post("/verify")
def verify(file: UploadFile = File(...)):
    data = _read_upload(file)
    try:
        seen = core.read(data)
    except core.BadImage as e:
        raise HTTPException(400, str(e))
    records = chain.all_records()
    rec = chain.lookup(seen["watermark_id"]) if seen["watermark_present"] else None
    v = verdict.decide(seen["watermark_present"], seen["watermark_id"], seen["fingerprint"], rec, records)
    if v["record"] is not None and not v["record"].tx_hash:
        chain.tx_hash_for(v["record"])
    return {
        "verdict": v["verdict"], "message": v["message"], "distance": v["distance"],
        "watermark_present": seen["watermark_present"], "watermark_id": seen["watermark_id"],
        "fingerprint": seen["fingerprint"],
        "record": _rec(v["record"]), "earlier": _rec(v.get("earlier")),
        "registry": {"address": chain.REGISTRY, "chain_id": chain.CHAIN_ID,
                     "url": chain.explorer_address(chain.REGISTRY)},
    }


@app.get("/record/{watermark_id}")
def record(watermark_id: str):
    rec = chain.lookup(watermark_id)
    if rec is None:
        raise HTTPException(404, "no such registration")
    return _rec(rec)


@app.get("/records")
def records(limit: int = 12):
    return {"count": chain.count(), "records": [_rec(r) for r in chain.recent_records(min(limit, 50))]}


@app.post("/stress")
def stress_run(file: UploadFile = File(...), other: UploadFile | None = File(None)):
    data = _read_upload(file)
    donor = _read_upload(other) if other is not None else None
    try:
        base = core.read(data)  # does the file you dropped actually carry a mark?
        rec = chain.lookup(base["watermark_id"]) if base["watermark_present"] else None
        log.info("stress baseline: mark_found=%s registered=%s", base["watermark_present"], rec is not None)
        return {
            "baseline": {"mark_found": base["watermark_present"], "registered": rec is not None},
            "results": stress.run(data, donor),
        }
    except core.BadImage as e:
        raise HTTPException(400, str(e))
