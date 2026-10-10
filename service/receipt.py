"""Verifiable registration receipts.

A receipt is a small JSON file that records one registration. It is signed by
the relayer (the key that paid the gas) and, when it is checked, every field is
cross-examined against the live registry: the fingerprint is hashed with the ID
to reproduce the EIP-712 challenge, the recorded signer is re-derived from the
passkey public key, and the stored transaction hash is looked up in the block
that the record claims. Change any field and at least one check fails.

The receipt is a convenience and a tamper-evidence layer, not a new source of
truth: the registry on Monad remains the truth.
"""
import json

from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct

from fingerprint import ALGORITHM as FINGERPRINT_ALGO

VERSION = 1
_HEX32 = set("0123456789abcdef")
# Receipts written before the field existed used this algorithm; treat a
# missing field as v1 so old receipts stay interpretable.
LEGACY_FINGERPRINT_ALGO = "phash-dct-16x16-v1"


def canonical(receipt: dict) -> bytes:
    """The bytes the relayer signs: every field except the signature itself."""
    body = {k: v for k, v in receipt.items() if k != "relayer_signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build(rec, qx: str | None, qy: str | None, chain_id: int, registry: str, tx_hash: str) -> dict:
    return {
        "imprint_receipt": VERSION,
        "chain_id": int(chain_id),
        "registry": Web3.to_checksum_address(registry),
        "watermark_id": rec.watermark_id.lower(),
        "fingerprint": "0x" + rec.fingerprint.lower(),
        "fingerprint_algo": FINGERPRINT_ALGO,
        "signer": rec.signer,
        "timestamp": int(rec.timestamp),
        "block": int(rec.block),
        "tx_hash": tx_hash,
        "passkey": {"qx": qx, "qy": qy} if qx and qy else None,
    }


def sign(receipt: dict, account) -> dict:
    msg = encode_defunct(primitive=canonical(receipt))
    sig = account.sign_message(msg)
    out = dict(receipt)
    out["relayer_signature"] = {"address": account.address, "signature": sig.signature.hex()}
    return out


def _is_hex32(v) -> bool:
    if not isinstance(v, str):
        return False
    h = v[2:] if v.startswith("0x") else v
    return len(h) == 64 and all(c in _HEX32 for c in h.lower())


def verify(receipt, chain, expected_relayer: str | None) -> dict:
    """Check a parsed receipt against the live registry. Never raises for a bad
    receipt: returns {valid, checks:[{name, ok, detail}], record}."""
    checks: list[dict] = []
    record_out = None

    def check(name: str, ok: bool, detail: str = "") -> bool:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    if not isinstance(receipt, dict):
        return {"valid": False, "checks": [{"name": "format", "ok": False, "detail": "not a JSON object"}], "record": None}

    fmt = (
        receipt.get("imprint_receipt") == VERSION
        and isinstance(receipt.get("chain_id"), int)
        and isinstance(receipt.get("timestamp"), int)
        and isinstance(receipt.get("block"), int)
        and _is_hex32(receipt.get("watermark_id"))
        and _is_hex32(receipt.get("fingerprint"))
        and isinstance(receipt.get("signer"), str)
        and isinstance(receipt.get("tx_hash"), str)
    )
    if not check("format", fmt, "version and field types"):
        return {"valid": False, "checks": checks, "record": None}

    algo = receipt.get("fingerprint_algo", LEGACY_FINGERPRINT_ALGO)
    check("fingerprint_algo", algo in (FINGERPRINT_ALGO, LEGACY_FINGERPRINT_ALGO),
          "fingerprint was computed with a supported algorithm version")

    registry_ok = False
    try:
        registry_ok = Web3.to_checksum_address(receipt["registry"]) == Web3.to_checksum_address(chain.REGISTRY)
    except Exception:
        registry_ok = False
    check("registry", receipt["chain_id"] == chain.CHAIN_ID and registry_ok,
          "receipt is for this chain and contract")
    check("challenge", _challenge_matches(receipt, chain), "fingerprint and ID reproduce the signed challenge")

    qx = qy = None
    pk = receipt.get("passkey")
    if isinstance(pk, dict) and _is_hex32(pk.get("qx")) and _is_hex32(pk.get("qy")):
        qx, qy = pk["qx"], pk["qy"]
        derived = chain.passkey_signer(qx, qy)
        check("passkey", derived.lower() == str(receipt["signer"]).lower(),
              "the recorded signer is the passkey public key's address")

    sig = receipt.get("relayer_signature")
    if isinstance(sig, dict) and isinstance(sig.get("signature"), str) and expected_relayer:
        try:
            recovered = Account.recover_message(
                encode_defunct(primitive=canonical(receipt)), signature=sig["signature"]
            )
            check("relayer_signature", recovered.lower() == expected_relayer.lower(),
                  "signed by this service's relayer")
        except Exception as e:
            check("relayer_signature", False, f"signature could not be checked: {e}")
    else:
        check("relayer_signature", False, "not signed (older or third-party receipt)")

    try:
        rec = chain.lookup(receipt["watermark_id"])
    except Exception as e:
        check("on_chain", False, f"could not read the registry: {e}")
        return {"valid": all(c["ok"] for c in checks), "checks": checks, "record": None}

    if rec is None:
        check("on_chain", False, "no such record on the registry")
    else:
        matches = (
            rec.signer.lower() == str(receipt["signer"]).lower()
            and rec.timestamp == receipt["timestamp"]
            and rec.block == receipt["block"]
            and ("0x" + rec.fingerprint.lower()) == receipt["fingerprint"].lower()
        )
        check("on_chain", matches, "signer, fingerprint, time and block match the registry")
        tx_ok = _tx_matches(rec, receipt["tx_hash"], chain)
        check("transaction", tx_ok, "the stored transaction hash is the registration's transaction")
        record_out = rec

    return {"valid": all(c["ok"] for c in checks), "checks": checks, "record": record_out}


def _challenge_matches(receipt: dict, chain) -> bool:
    try:
        derived = chain.challenge_for(receipt["watermark_id"], receipt["fingerprint"])  # returns 0x hex
    except Exception:
        return False
    stored = receipt.get("challenge")
    if isinstance(stored, str) and _is_hex32(stored):
        return derived.lower() == stored.lower()
    return bool(derived)  # challenge can always be re-derived from the id + fingerprint


def _tx_matches(rec, tx_hash: str, chain) -> bool:
    if not rec.block:
        return False
    try:
        return (rec.tx_hash or "").lower() == tx_hash.lower() if rec.tx_hash else _lookup_tx(rec, tx_hash, chain)
    except Exception:
        return False


def _lookup_tx(rec, tx_hash: str, chain) -> bool:
    found = chain.tx_hash_for(rec)
    if not found:
        return False
    return found.lower() == tx_hash.lower()
