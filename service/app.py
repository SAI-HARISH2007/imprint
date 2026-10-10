"""HTTP face of Imprint. Run:  uvicorn app:app --port 8000"""
import datetime as dt
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

import chain
import core
import fingerprint
import limits
import receipt as receipts
import stress
import verdict

MAX_BYTES = 30 * 1024 * 1024
HEX32 = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")
HEX = re.compile(r"^(0x)?[0-9a-fA-F]*$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    core.payload_bits()  # load the model once at startup, not on the first request
    yield


app = FastAPI(title="Imprint", lifespan=lifespan)


def _cors_origins() -> list[str]:
    raw = os.getenv("IMPRINT_CORS_ORIGINS", "*")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["*"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["content-type"],
)


log = logging.getLogger("uvicorn.error")

if "*" in _cors_origins():
    log.warning(
        "IMPRINT_CORS_ORIGINS is '*' (any website may call this API). Set it to your "
        "frontend origin(s) for a public deployment."
    )


# ---------------------------------------------------------------- limits
# Registration attempts cost an RPC round-trip; successful registrations cost
# gas. They are budgeted separately so a flood of bad signatures cannot drain
# the relayer, and a successful flood cannot drain it silently either.
PER_IP_ATTEMPTS_HOUR = int(os.getenv("IMPRINT_PER_IP_ATTEMPTS_HOUR", "30"))
PER_IP_PER_HOUR = int(os.getenv("IMPRINT_PER_IP_HOUR", "12"))
GLOBAL_PER_DAY = int(os.getenv("IMPRINT_GLOBAL_DAY", "150"))
HEAVY_PER_MIN = int(os.getenv("IMPRINT_HEAVY_PER_MIN", "20"))
MAX_BUSY = int(os.getenv("IMPRINT_MAX_BUSY", "2"))

_attempts = limits.Limiter(PER_IP_ATTEMPTS_HOUR, 3600, "register attempts")
_successes = limits.Limiter(PER_IP_PER_HOUR, 3600, "registrations")
_daily = limits.Limiter(GLOBAL_PER_DAY, 86400, "daily registrations")
_heavy = limits.Limiter(HEAVY_PER_MIN, 60, "expensive requests")
_busy = limits.ConcurrencyCap(MAX_BUSY)

def _ip(request: Request) -> str:
    peer = request.client.host if request.client else None
    return limits.client_ip(peer, request.headers.get("x-forwarded-for"))


def _http_rate(e: limits.RateLimited, message: str) -> HTTPException:
    return HTTPException(429, message, headers={"Retry-After": str(e.retry_after)})


def _read_upload(file: UploadFile) -> bytes:
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file is larger than 30 MB")
    name = re.sub(r"[\r\n\t]", " ", (file.filename or "?"))[:120]
    log.info("upload %s: %d bytes, %s", name, len(data), file.content_type)
    return data


def _heavy_request(request: Request) -> None:
    """Common throttle for the model- and RPC-heavy endpoints."""
    try:
        _heavy.take(_ip(request))
    except limits.RateLimited as e:
        raise _http_rate(e, "Too many requests from this connection. Try again in a moment.") from e
    try:
        return _busy.slot()
    except limits.Busy as e:
        raise HTTPException(503, "The service is busy; please retry shortly.", headers={"Retry-After": "5"}) from e


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


# ---------------------------------------------------------------- models
class Assertion(BaseModel):
    r: Annotated[str, Field(max_length=66)]
    s: Annotated[str, Field(max_length=66)]
    challengeIndex: Annotated[int, Field(ge=0, le=4096)]
    typeIndex: Annotated[int, Field(ge=0, le=4096)]
    authenticatorData: Annotated[str, Field(max_length=8192)]
    clientDataJSON: Annotated[str, Field(max_length=4096)]

    @field_validator("r", "s")
    @classmethod
    def _hex32(cls, v: str) -> str:
        if not HEX32.match(v):
            raise ValueError("must be a 32-byte hex string")
        return v

    @field_validator("authenticatorData")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not HEX.match(v):
            raise ValueError("must be hex")
        return v


class RegisterBody(BaseModel):
    watermark_id: Annotated[str, Field(max_length=66)]
    fingerprint: Annotated[str, Field(max_length=66)]
    auth: Assertion
    qx: Annotated[str, Field(max_length=66)]
    qy: Annotated[str, Field(max_length=66)]

    @field_validator("watermark_id", "fingerprint", "qx", "qy")
    @classmethod
    def _hex32(cls, v: str) -> str:
        if not HEX32.match(v):
            raise ValueError("must be a 32-byte hex string")
        return v


class ReceiptBody(BaseModel):
    receipt: dict


# ---------------------------------------------------------------- endpoints
@app.get("/health")
def health():
    return {"ok": True, "payload_bits": core.payload_bits(), "busy": _busy.active, "max_busy": MAX_BUSY}


@app.get("/config")
def config():
    return {
        "chain_id": chain.CHAIN_ID, "registry": chain.REGISTRY,
        "registry_url": chain.explorer_address(chain.REGISTRY), "explorer": chain.EXPLORER,
        "fingerprint": {"algorithm": fingerprint.ALGORITHM, "version": fingerprint.VERSION,
                        "bits": fingerprint.BIT_LEN, "hex_length": fingerprint.HEX_LEN},
        "thresholds": {"match": verdict.T_MATCH, "near": verdict.T_NEAR, "duplicate": verdict.T_DUP},
    }


@app.get("/status")
def status():
    """Launch diagnostics: is the RPC up, is the registry deployed, is the relayer funded?"""
    out = {"ok": False}
    try:
        w3 = chain.w3()
        connected = bool(w3.is_connected())
        block = int(w3.eth.block_number) if connected else None
        chain_id = int(w3.eth.chain_id) if connected else None
    except Exception as e:
        connected, block, chain_id = False, None, None
        out["rpc_error"] = str(e)[:200]
    out["rpc"] = {"connected": connected, "block": block, "chain_id": chain_id,
                  "matches_expected": chain_id == chain.CHAIN_ID}

    reg = {"address": chain.REGISTRY, "deployed": False, "count": None}
    try:
        code = chain.w3().eth.get_code(chain.REGISTRY)
        reg["deployed"] = len(code) > 0
        if reg["deployed"]:
            reg["count"] = chain.count(fresh=True)
    except Exception as e:
        reg["error"] = str(e)[:200]
    out["registry"] = reg

    rel = {"configured": False, "address": None, "balance_wei": None, "low": None}
    try:
        acct = chain._relayer_account()
        rel["configured"] = True
        rel["address"] = acct.address
        bal = int(chain.w3().eth.get_balance(acct.address))
        if os.getenv("IMPRINT_STATUS_SHOW_BALANCE", "").lower() in ("1", "true", "yes"):
            rel["balance_wei"] = str(bal)
        rel["low"] = bal < int(os.getenv("IMPRINT_LOW_BALANCE_WEI", str(5 * 10**17)))
    except chain.RelayError:
        pass
    except Exception as e:
        rel["error"] = str(e)[:200]
    out["relayer"] = rel

    out["ok"] = connected and reg["deployed"] and chain_id == chain.CHAIN_ID
    return out


@app.post("/mark")
def mark(request: Request, file: UploadFile = File(...)):
    with _heavy_request(request):
        data = _read_upload(file)
        try:
            out = core.mark(data)
            log.info("mark %dx%d strength=%s self_test=%s", out["width"], out["height"], out["strength"], out["self_test"])
            return out
        except core.BadImage as e:
            raise HTTPException(400, str(e))


@app.post("/check")
def check(request: Request, file: UploadFile = File(...)):
    """Raw read: the hidden ID (if any) and the fingerprint, with no registry lookup."""
    with _heavy_request(request):
        data = _read_upload(file)
        try:
            return core.read(data)
        except core.BadImage as e:
            raise HTTPException(400, str(e))


@app.get("/challenge")
def challenge(watermark_id: str, fingerprint: str):
    _require_hex32(watermark_id, "watermark_id")
    _require_hex32(fingerprint, "fingerprint")
    return {"challenge": chain.challenge_for(watermark_id, fingerprint)}


@app.get("/signer")
def signer(qx: str, qy: str):
    """The registry signer address for a passkey public key (same derivation as the contract)."""
    _require_hex32(qx, "qx")
    _require_hex32(qy, "qy")
    return {"signer": chain.passkey_signer(qx, qy)}


@app.post("/register")
def register(body: RegisterBody, request: Request):
    ip = _ip(request)
    try:
        _attempts.take(ip)
    except limits.RateLimited as e:
        raise _http_rate(e, "Too many registration attempts from this connection. Try again later.") from e

    # Squatting guard: refuse an image that looks like an earlier registration by someone else.
    # Re-registering your own image with your own passkey is allowed.
    # (Checked before the gas quota so a refused duplicate does not use up the visitor's quota.)
    me = chain.passkey_signer(body.qx, body.qy).lower()
    others = [r for r in chain.near_records(body.fingerprint, verdict.T_DUP) if r.signer.lower() != me]
    lookalike = verdict.find_near_duplicate(body.fingerprint, others)
    if lookalike:
        rec, d = lookalike
        chain.tx_hash_for(rec)
        raise HTTPException(409, {
            "error": "near_duplicate",
            "message": "This image looks like one that was already registered by someone else.",
            "distance": d, "earlier": _rec(rec),
        })

    # Reserve gas quota only now, and only for work we intend to submit.
    try:
        _successes.take(ip)
        _daily.take("all")
    except limits.RateLimited as e:
        if e.retry_after > 3600:
            raise _http_rate(e, "The demo has reached its daily registration limit.") from e
        raise _http_rate(e, "Too many registrations from this connection. Try again later.") from e

    try:
        res = chain.register_passkey(body.watermark_id, body.fingerprint, body.auth.model_dump(), body.qx, body.qy)
    except chain.RelayError as e:
        raise HTTPException(400, str(e))
    rec = res.pop("record")
    out = {**res, "record": _rec(rec)}
    out["receipt"] = _build_receipt(rec, body.qx, body.qy, res.get("tx_hash", ""))
    return out


@app.post("/receipt/verify")
def receipt_verify(body: ReceiptBody):
    """Check a registration receipt against the live registry. Read-only."""
    expected = None
    try:
        expected = chain._relayer_account().address
    except Exception:
        pass
    try:
        return receipts.verify(body.receipt, chain, expected)
    except Exception as e:
        raise HTTPException(400, f"could not check that receipt: {e}")


@app.post("/verify")
def verify(request: Request, file: UploadFile = File(...)):
    with _heavy_request(request):
        data = _read_upload(file)
        try:
            seen = core.read(data)
        except core.BadImage as e:
            raise HTTPException(400, str(e))
        records = chain.near_records(seen["fingerprint"], verdict.T_NEAR)
        rec = chain.lookup(seen["watermark_id"]) if seen["watermark_present"] else None
        v = verdict.decide(seen["watermark_present"], seen["watermark_id"], seen["fingerprint"], rec, records)
        if v["record"] is not None and not v["record"].tx_hash:
            chain.tx_hash_for(v["record"])
        return {
            "verdict": v["verdict"], "message": v["message"], "distance": v["distance"],
            "watermark_present": seen["watermark_present"], "watermark_id": seen["watermark_id"],
            "fingerprint": seen["fingerprint"], "algorithm": fingerprint.ALGORITHM,
            "record": _rec(v["record"]), "earlier": _rec(v.get("earlier")),
            "registry": {"address": chain.REGISTRY, "chain_id": chain.CHAIN_ID,
                         "url": chain.explorer_address(chain.REGISTRY)},
        }


@app.get("/record/{watermark_id}")
def record(watermark_id: str):
    _require_hex32(watermark_id, "watermark_id")
    rec = chain.lookup(watermark_id)
    if rec is None:
        raise HTTPException(404, "no such registration")
    return _rec(rec)


@app.get("/records")
def records(limit: int = 12, signer: str | None = None):
    """Recent registrations, or all registrations by one signer (for a 'my work' view)."""
    n = max(1, min(limit, 50))
    if signer:
        if not re.match(r"^0x[0-9a-fA-F]{40}$", signer):
            raise HTTPException(422, "signer must be a 20-byte address")
        want = signer.lower()
        rows = [r for r in reversed(chain.all_records()) if r.signer.lower() == want]
        return {"count": len(rows), "records": [_rec(r) for r in rows[:n]]}
    return {"count": chain.count(), "records": [_rec(r) for r in chain.recent_records(n)]}


@app.post("/stress")
def stress_run(request: Request, file: UploadFile = File(...), other: UploadFile | None = File(None)):
    with _heavy_request(request):
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


# ---------------------------------------------------------------- helpers
def _require_hex32(value: str, field: str) -> None:
    if not isinstance(value, str) or not HEX32.match(value):
        raise HTTPException(422, f"{field} must be a 32-byte hex string")


def _build_receipt(rec, qx: str, qy: str, tx_hash: str):
    try:
        receipt = receipts.build(rec, qx, qy, chain.CHAIN_ID, chain.REGISTRY, tx_hash)
    except Exception as e:
        log.warning("could not build receipt: %s", e)
        return None
    try:
        account = chain._relayer_account()
        return receipts.sign(receipt, account)
    except chain.RelayError:
        return receipt  # unsigned, still cross-checkable against the chain
    except Exception as e:
        log.warning("could not sign receipt: %s", e)
        return receipt


@app.exception_handler(chain.BadInput)
async def _bad_input_handler(request: Request, exc: chain.BadInput):
    return JSONResponse(status_code=422, content={"detail": str(exc)})
