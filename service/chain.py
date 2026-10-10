"""Everything that touches Monad: read records, scan registrations, relay a passkey registration.

The relayer pays gas, so a visitor needs no wallet funds. The contract still checks the passkey
signature, so the relayer cannot register anything in someone else's name.
"""
import json
import os
import threading
import time
from pathlib import Path

from web3 import Web3

import fingerprint
import index
from verdict import Record

RPC_URL = os.getenv("IMPRINT_RPC", "https://testnet-rpc.monad.xyz")
CHAIN_ID = int(os.getenv("IMPRINT_CHAIN_ID", "10143"))
REGISTRY = os.getenv("IMPRINT_REGISTRY", "0xf4a792ddb0c83Bdf1Ed2E1220B197760d821396c")
DEPLOY_BLOCK = int(os.getenv("IMPRINT_DEPLOY_BLOCK", "69296432"))
EXPLORER = os.getenv("IMPRINT_EXPLORER", "https://testnet.monadvision.com")

_ABI = json.loads((Path(__file__).parent / "abi.json").read_text())
_lock = threading.Lock()
_w3: Web3 | None = None
_contract = None

# in-memory copy of the registry, filled with plain eth_calls (count + recordsPage), no log scan
_records: dict[str, Record] = {}
_next_index = 0
_scan_lock = threading.RLock()
_tx_cache: dict[str, str] = {}
_count_cache: tuple[float, int] = (0.0, -1)
COUNT_TTL = float(os.getenv("IMPRINT_COUNT_TTL", "10"))
PAGE = 100

# A BK-tree over the fingerprints already in _records, for near-duplicate search.
# Measured (test_index.py, 5000 random 256-bit keys): the BK-tree is ~1.0x at
# radius 10 and slower at radius 16/24, because a registry that rejects
# near-duplicates is essentially spread out, leaving the tree nothing to prune.
# So the linear scan stays the default and the tree is an opt-in A/B path
# (IMPRINT_INDEX=1). It is kept correct and tested for when fingerprints cluster.
INDEX_ENABLED = os.getenv("IMPRINT_INDEX", "0").strip().lower() in ("1", "true", "yes")
_index = index.BKTree()
_indexed_ids: set[str] = set()


class RelayError(Exception):
    pass


class BadInput(ValueError):
    """A caller-supplied hex string was not valid. Maps to HTTP 400/422."""


_gas_price_cache: tuple[float, int] = (0.0, 0)


def _gas_price() -> int:
    """Gas price, refreshed at most once a minute. It barely moves on testnet."""
    global _gas_price_cache
    t, p = _gas_price_cache
    if time.time() - t > 60 or p == 0:
        p = w3().eth.gas_price
        _gas_price_cache = (time.time(), p)
    return p


def w3() -> Web3:
    global _w3, _contract
    if _w3 is None:
        _w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 30}))
        _contract = _w3.eth.contract(address=Web3.to_checksum_address(REGISTRY), abi=_ABI)
    return _w3


def contract():
    w3()
    return _contract


def _b32(x: str, field: str = "value") -> bytes:
    """Hex string -> exactly 32 bytes. Raises BadInput (never ValueError) on anything else."""
    if not isinstance(x, str):
        raise BadInput(f"{field} must be a hex string")
    h = x[2:] if x.startswith("0x") or x.startswith("0X") else x
    if not h:
        raise BadInput(f"{field} must not be empty")
    if len(h) > 64:
        raise BadInput(f"{field} is longer than 32 bytes")
    if len(h) % 2:
        h = "0" + h
    try:
        raw = bytes.fromhex(h)
    except ValueError as e:
        raise BadInput(f"{field} is not valid hex") from e
    return raw.rjust(32, b"\x00")


def _hexbytes(x: str, field: str = "value") -> bytes:
    """Arbitrary-length hex string -> bytes. Raises BadInput on bad hex."""
    if not isinstance(x, str):
        raise BadInput(f"{field} must be a hex string")
    h = x[2:] if x.startswith("0x") or x.startswith("0X") else x
    if len(h) % 2:
        h = "0" + h
    try:
        return bytes.fromhex(h)
    except ValueError as e:
        raise BadInput(f"{field} is not valid hex") from e


def _hex32(b: bytes) -> str:
    return "0x" + bytes(b).hex()


def explorer_tx(tx_hash: str) -> str:
    return f"{EXPLORER}/tx/{tx_hash}"


def explorer_address(addr: str) -> str:
    return f"{EXPLORER}/address/{addr}"


def _relayer_account():
    key = os.getenv("IMPRINT_RELAYER_KEY")
    if not key:
        path = Path(os.getenv("IMPRINT_RELAYER_KEY_FILE", str(Path.home() / ".imprint" / "deployer.json")))
        if not path.exists():
            raise RelayError("relayer key is not configured")
        data = json.loads(path.read_text())
        key = data["data"][0]["private_key"] if "data" in data else data["private_key"]
    return w3().eth.account.from_key(key)


# ---------------------------------------------------------------- reads

def _fp_hex(b: bytes) -> str:
    return bytes(b).hex()  # 64 hex chars, no 0x, same form the image service produces


def _to_record(wid: bytes, tup) -> Record:
    signer, ts, block, fp = tup
    return Record(watermark_id=_hex32(wid).lower(), fingerprint=_fp_hex(fp), signer=signer,
                  timestamp=int(ts), block=int(block))


def get_record(watermark_id: str) -> Record | None:
    tup = contract().functions.recordOf(_b32(watermark_id)).call()
    if tup[1] == 0:
        return None
    return _to_record(_b32(watermark_id), tup)


def challenge_for(watermark_id: str, fingerprint_hex: str) -> str:
    return _hex32(contract().functions.challengeFor(_b32(watermark_id), _b32(fingerprint_hex)).call())


def passkey_signer(qx: str, qy: str) -> str:
    """Same derivation as the contract: address(uint160(keccak256(abi.encode(qx, qy))))."""
    digest = Web3.keccak(_b32(qx) + _b32(qy))
    return Web3.to_checksum_address(digest[-20:])


def count(fresh: bool = False) -> int:
    """Registration count, cached for COUNT_TTL seconds so a busy verifier does not
    hammer the RPC with the same eth_call."""
    global _count_cache
    t, n = _count_cache
    if fresh or n < 0 or time.time() - t > COUNT_TTL:
        n = int(contract().functions.count().call())
        _count_cache = (time.time(), n)
    return n


def _index_record(r: Record) -> None:
    """Add a record to the fingerprint index once. Caller holds nothing special."""
    if not INDEX_ENABLED or r.watermark_id in _indexed_ids:
        return
    try:
        fpi = fingerprint.from_hex(r.fingerprint)
    except ValueError:
        return
    _index.add(fpi, r.watermark_id)
    _indexed_ids.add(r.watermark_id)


def refresh_index() -> None:
    """Pull any new registrations with plain contract calls. Works on any RPC, no indexer."""
    global _next_index
    with _scan_lock:
        n = count()
        while _next_index < n:
            ids, recs = contract().functions.recordsPage(_next_index, PAGE).call()
            if not ids:
                break
            for wid, tup in zip(ids, recs):
                r = _to_record(wid, tup)
                _records[r.watermark_id] = r
                _index_record(r)
            _next_index += len(ids)


def all_records() -> list[Record]:
    refresh_index()
    return sorted(_records.values(), key=lambda r: (r.timestamp, r.block))


def near_records(fp_hex: str, threshold: int) -> list[Record]:
    """Records whose fingerprint is within `threshold` bits of fp_hex.

    Uses the BK-tree when enabled, otherwise every record (the caller then
    filters). Correctness is identical either way: the tree only prunes
    fingerprints that cannot be within the radius."""
    refresh_index()
    if not INDEX_ENABLED:
        return all_records()
    try:
        key = fingerprint.from_hex(fp_hex)
    except ValueError:
        return []
    with _scan_lock:
        hits = _index.search(key, threshold)
    return [_records[wid] for _, wid in hits if wid in _records]


def recent_records(limit: int = 20) -> list[Record]:
    return list(reversed(all_records()))[:limit]


def tx_hash_for(rec: Record) -> str:
    """Find the registration transaction with a one-block log query (the record stores its block)."""
    if rec.tx_hash:
        return rec.tx_hash
    if rec.watermark_id in _tx_cache:
        rec.tx_hash = _tx_cache[rec.watermark_id]
        return rec.tx_hash
    try:
        logs = contract().events.Registered().get_logs(
            from_block=rec.block, to_block=rec.block,
            argument_filters={"watermarkId": _b32(rec.watermark_id)},
        )
        if logs:
            h = _hex32(logs[0]["transactionHash"])
            _tx_cache[rec.watermark_id] = h
            rec.tx_hash = h
            return h
    except Exception:
        pass
    return ""


def lookup(watermark_id: str) -> Record | None:
    """The contract is the source of truth."""
    rec = get_record(watermark_id)
    if rec:
        tx_hash_for(rec)
    return rec


# ---------------------------------------------------------------- relay

def _landed(watermark_id: str, timeout: float) -> Record | None:
    """Poll for a record that may have landed even if we lost the receipt."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            rec = get_record(watermark_id)
        except Exception:
            rec = None
        if rec is not None:
            return rec
        time.sleep(0.5)
    return None


def register_passkey(watermark_id: str, fingerprint_hex: str, auth: dict, qx: str, qy: str) -> dict:
    c = contract()
    auth_tuple = (
        _b32(auth["r"], "r"), _b32(auth["s"], "s"),
        int(auth["challengeIndex"]), int(auth["typeIndex"]),
        _hexbytes(auth["authenticatorData"], "authenticatorData"),
        auth["clientDataJSON"],
    )
    fn = c.functions.registerPasskey(_b32(watermark_id), _b32(fingerprint_hex), auth_tuple, _b32(qx), _b32(qy))
    acct = _relayer_account()
    with _lock:
        try:
            gas = fn.estimate_gas({"from": acct.address})  # reverts here if the signature or ID is bad
        except Exception as e:
            raise RelayError(_explain_revert(e)) from e
        # Monad charges for the gas limit, not gas used, so keep the margin small.
        tx = fn.build_transaction({
            "from": acct.address,
            "nonce": w3().eth.get_transaction_count(acct.address, "pending"),
            "gas": int(gas * 1.15),
            "chainId": CHAIN_ID,
            "gasPrice": _gas_price(),
        })
        signed = acct.sign_transaction(tx)
        t0 = time.time()
        try:
            h = w3().eth.send_raw_transaction(signed.raw_transaction)
        except Exception as e:
            # A "nonce too low" / "already known" here usually means a previous
            # attempt of this same registration already landed.
            rec = _landed(watermark_id, 6)
            if rec is not None:
                return _success(rec, rec.tx_hash, 0, 0, 0, t0)
            raise RelayError(_explain_revert(e)) from e
        h = _hex32(h)
        try:
            receipt = w3().eth.wait_for_transaction_receipt(h, timeout=60, poll_latency=0.25)
        except Exception:
            # The transaction was broadcast; we just did not see the receipt in
            # time. It may still confirm, so check the registry before failing.
            rec = _landed(watermark_id, 30)
            if rec is not None:
                return _success(rec, h, 0, int(gas * 1.15), 0, t0)
            raise RelayError("the registration was submitted but not confirmed in time; check again shortly")
    if receipt["status"] != 1:
        raise RelayError("transaction reverted")
    rec = get_record(watermark_id)  # one call: signer, timestamp, block, fingerprint
    if rec:
        rec.tx_hash = h
        _tx_cache[rec.watermark_id] = rec.tx_hash
        with _scan_lock:
            _records[rec.watermark_id] = rec  # visible to readers now; the page index catches up on its own
            _index_record(rec)
    if rec is None:
        raise RelayError("the transaction confirmed but the record could not be read back")
    return _success(rec, h, int(receipt["gasUsed"]), int(tx["gas"]),
                    int(receipt.get("effectiveGasPrice", tx.get("gasPrice", 0))), t0)


def _success(rec: Record, tx_hash: str, gas_used: int, gas_limit: int, gas_price: int, t0: float) -> dict:
    return {
        "tx_hash": tx_hash, "block": int(rec.block),
        "timestamp": rec.timestamp,
        "gas_used": int(gas_used), "gas_limit": int(gas_limit), "gas_price": int(gas_price),
        "seconds": round(time.time() - t0, 2),
        "signer": rec.signer,
        "record": rec,
        "explorer_url": explorer_tx(tx_hash) if tx_hash else None,
    }


def _explain_revert(e: Exception) -> str:
    s = str(e)
    if "AlreadyRegistered" in s or "0x" in s and "already" in s.lower():
        return "that ID is already registered"
    if "BadSignature" in s:
        return "the passkey signature did not verify"
    if "ZeroId" in s:
        return "invalid ID"
    return "the registry rejected this registration"
