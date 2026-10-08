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
_scan_lock = threading.Lock()
_tx_cache: dict[str, str] = {}
PAGE = 100


class RelayError(Exception):
    pass


def w3() -> Web3:
    global _w3, _contract
    if _w3 is None:
        _w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 30}))
        _contract = _w3.eth.contract(address=Web3.to_checksum_address(REGISTRY), abi=_ABI)
    return _w3


def contract():
    w3()
    return _contract


def _b32(x: str) -> bytes:
    h = x[2:] if x.startswith("0x") else x
    return bytes.fromhex(h.rjust(64, "0"))


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
    return contract().functions.passkeySigner(_b32(qx), _b32(qy)).call()


def count() -> int:
    return int(contract().functions.count().call())


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
            _next_index += len(ids)


def all_records() -> list[Record]:
    refresh_index()
    return sorted(_records.values(), key=lambda r: (r.timestamp, r.block))


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

def register_passkey(watermark_id: str, fingerprint_hex: str, auth: dict, qx: str, qy: str) -> dict:
    c = contract()
    auth_tuple = (
        _b32(auth["r"]), _b32(auth["s"]), int(auth["challengeIndex"]), int(auth["typeIndex"]),
        bytes.fromhex(auth["authenticatorData"].removeprefix("0x")), auth["clientDataJSON"],
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
            "gasPrice": w3().eth.gas_price,
        })
        signed = acct.sign_transaction(tx)
        t0 = time.time()
        h = w3().eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3().eth.wait_for_transaction_receipt(h, timeout=60, poll_latency=0.25)
    if receipt["status"] != 1:
        raise RelayError("transaction reverted")
    block = w3().eth.get_block(receipt["blockNumber"])
    rec = get_record(watermark_id)
    return {
        "tx_hash": _hex32(h), "block": int(receipt["blockNumber"]), "timestamp": int(block["timestamp"]),
        "gas_used": int(receipt["gasUsed"]), "gas_limit": int(tx["gas"]),
        "seconds": round(time.time() - t0, 2),
        "signer": rec.signer if rec else None,
        "explorer_url": explorer_tx(_hex32(h)),
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
