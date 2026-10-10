"""Tests for the hardening added to the service: rate limits, client IP, input
validation and registration receipts. These do not need the image model or a
live chain, so they run everywhere."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

import limits
import receipt as receipts
from eth_account import Account
from web3 import Web3


# ---------------------------------------------------------------- limits
def test_limiter_take_and_check():
    lim = limits.Limiter(2, 60, "t")
    lim.take("a")
    lim.take("a")
    with pytest.raises(limits.RateLimited):
        lim.take("a")
    # a different key is unaffected
    lim.take("b")
    assert lim.used("a") == 2


def test_limiter_check_does_not_spend():
    lim = limits.Limiter(1, 60, "t")
    lim.check("a")  # nothing recorded
    lim.take("a")
    with pytest.raises(limits.RateLimited):
        lim.check("a")


def test_limiter_zero_means_disabled():
    lim = limits.Limiter(0, 60, "t")
    for _ in range(100):
        lim.take("a")
    assert lim.used("a") == 0


def test_limiter_window_expires():
    lim = limits.Limiter(1, 0.05, "t")
    lim.take("a")
    with pytest.raises(limits.RateLimited):
        lim.take("a")
    time.sleep(0.1)
    lim.take("a")


def test_limiter_key_dict_stays_bounded():
    lim = limits.Limiter(1, 3600, "t")
    for i in range(limits.MAX_KEYS + 50):
        lim.take(f"k{i}")
    assert len(lim._q) <= limits.MAX_KEYS + 1


def test_concurrency_cap_bounds_work():
    cap = limits.ConcurrencyCap(1)
    entered = []

    def worker():
        with cap.slot():
            entered.append(1)
            time.sleep(0.15)

    t1 = threading.Thread(target=worker)
    t1.start()
    time.sleep(0.03)
    with pytest.raises(limits.Busy):
        with cap.slot():
            pass
    t1.join()
    assert entered == [1]


def test_client_ip_uses_rightmost_hop_by_default():
    # a client-supplied left hand value must not decide the key
    ip = limits.client_ip("10.0.0.9", "1.2.3.4, 5.6.7.8, 203.0.113.7")
    assert ip == "203.0.113.7"


def test_client_ip_ignores_xff_from_untrusted_peer(monkeypatch):
    monkeypatch.setenv("IMPRINT_TRUSTED_PROXIES", "127.0.0.1")
    assert limits.client_ip("8.8.8.8", "1.2.3.4") == "8.8.8.8"


def test_client_ip_falls_back_to_peer_without_header():
    assert limits.client_ip("203.0.113.7", None) == "203.0.113.7"


# ---------------------------------------------------------------- receipts
REG = Web3.to_checksum_address("0x00000000000000000000000000000000000000A1")
SIGNER = Web3.to_checksum_address("0x00000000000000000000000000000000000000B2")
QX = "0x" + "11" * 32
QY = "0x" + "22" * 32
FP = "aa" * 32
WID = "0x" + "cc" * 32


class FakeRecord:
    def __init__(self, **kw):
        self.watermark_id = kw.get("watermark_id", WID)
        self.fingerprint = kw.get("fingerprint", FP)
        self.signer = kw.get("signer", SIGNER)
        self.timestamp = kw.get("timestamp", 1_800_000_000)
        self.block = kw.get("block", 69484467)
        self.tx_hash = kw.get("tx_hash", "0x" + "dd" * 32)


class FakeChain:
    CHAIN_ID = 10143
    REGISTRY = REG
    relay = "0x" + "ab" * 32

    def __init__(self, rec):
        self.rec = rec

    def challenge_for(self, watermark_id, fingerprint_hex):
        return "0x" + "ab" * 32

    def passkey_signer(self, qx, qy):
        return self.rec.signer

    def lookup(self, watermark_id):
        return self.rec if watermark_id.lower() == self.rec.watermark_id.lower() else None

    def tx_hash_for(self, rec):
        return rec.tx_hash


def make_receipt():
    rec = FakeRecord()
    r = receipts.build(rec, QX, QY, FakeChain.CHAIN_ID, FakeChain.REGISTRY, rec.tx_hash)
    acct = Account.from_key("0x" + "42" * 32)
    return rec, r, acct


def test_receipt_round_trip_verifies():
    rec, r, acct = make_receipt()
    signed = receipts.sign(r, acct)
    out = receipts.verify(signed, FakeChain(rec), acct.address)
    assert out["valid"] is True
    assert all(c["ok"] for c in out["checks"])
    assert out["record"] is rec


def test_receipt_tamper_breaks_signature():
    rec, r, acct = make_receipt()
    signed = receipts.sign(r, acct)
    signed["block"] = signed["block"] + 1  # edit one field
    out = receipts.verify(signed, FakeChain(rec), acct.address)
    assert out["valid"] is False
    sig = next(c for c in out["checks"] if c["name"] == "relayer_signature")
    assert sig["ok"] is False


def test_receipt_without_signature_is_not_valid_but_chain_checks_run():
    rec, r, _ = make_receipt()
    out = receipts.verify(r, FakeChain(rec), None)
    assert out["valid"] is False
    on_chain = next(c for c in out["checks"] if c["name"] == "on_chain")
    assert on_chain["ok"] is True


def test_receipt_rejects_a_different_registry():
    rec, r, acct = make_receipt()
    r = dict(r, chain_id=1)
    out = receipts.verify(r, FakeChain(rec), acct.address)
    assert out["valid"] is False
    assert next(c for c in out["checks"] if c["name"] == "registry")["ok"] is False


def test_receipt_rejects_garbage():
    out = receipts.verify({"nonsense": 1}, FakeChain(FakeRecord()), None)
    assert out["valid"] is False
    assert out["checks"][0]["name"] == "format"


# ---------------------------------------------------------------- HTTP validation
@pytest.fixture()
def client():
    import app as app_module

    return TestClient(app_module.app)


def test_register_rejects_bad_hex(client):
    r = client.post("/register", json={
        "watermark_id": "not-hex",
        "fingerprint": FP,
        "auth": {"r": "0x" + "11" * 32, "s": "0x" + "22" * 32, "challengeIndex": 0,
                 "typeIndex": 0, "authenticatorData": "0x00", "clientDataJSON": "{}"},
        "qx": QX, "qy": QY,
    })
    assert r.status_code == 422


def test_register_rejects_missing_fields(client):
    assert client.post("/register", json={"watermark_id": WID}).status_code == 422


def test_challenge_rejects_bad_hex(client):
    assert client.get("/challenge", params={"watermark_id": "xyz", "fingerprint": FP}).status_code == 422
    assert client.get("/challenge", params={"watermark_id": WID, "fingerprint": "nope"}).status_code == 422


def test_record_rejects_bad_id(client):
    assert client.get("/record/not-a-hash").status_code == 422


def test_signer_rejects_bad_key(client):
    assert client.get("/signer", params={"qx": "nope", "qy": QY}).status_code == 422


def test_records_limit_is_bounded(client, monkeypatch):
    monkeypatch.setattr("chain.recent_records", lambda n: [])
    monkeypatch.setattr("chain.count", lambda fresh=False: 0)
    r = client.get("/records", params={"limit": -5})
    assert r.status_code == 200
    r = client.get("/records", params={"limit": 9999})
    assert r.status_code == 200


def test_receipt_verify_endpoint_handles_garbage(client):
    r = client.post("/receipt/verify", json={"receipt": {"hello": "world"}})
    assert r.status_code == 200
    assert r.json()["valid"] is False


# ---------------------------------------------------------------- mark/register claim race
def _assertion_json():
    return {"r": "0x" + "11" * 32, "s": "0x" + "22" * 32, "challengeIndex": 0,
            "typeIndex": 0, "authenticatorData": "0x00", "clientDataJSON": "{}"}


def _register_body(**over):
    body = {"watermark_id": WID, "fingerprint": FP, "auth": _assertion_json(), "qx": QX, "qy": QY}
    body.update(over)
    return body


def _fake_register_ok(monkeypatch, rec):
    monkeypatch.setattr("chain.passkey_signer", lambda qx, qy: rec.signer)
    monkeypatch.setattr("chain.near_records", lambda fp_hex, threshold: [])
    monkeypatch.setattr(
        "chain.register_passkey",
        lambda *a, **k: {"tx_hash": rec.tx_hash, "block": rec.block, "timestamp": rec.timestamp,
                         "gas_used": 1, "gas_limit": 2, "seconds": 0.1, "signer": rec.signer,
                         "record": rec, "explorer_url": "https://example/tx"},
    )


def test_register_reveals_image_for_a_matching_claim(client, monkeypatch):
    import app as app_module

    rec = FakeRecord()
    _fake_register_ok(monkeypatch, rec)
    token = app_module._claims.put(WID, FP, "MARKED_BYTES", ip="test").token

    r = client.post("/register", json=_register_body(claim=token))
    assert r.status_code == 200, r.text
    assert r.json().get("image_png_base64") == "MARKED_BYTES"


def test_register_without_a_claim_reveals_no_image(client, monkeypatch):
    rec = FakeRecord()
    _fake_register_ok(monkeypatch, rec)
    r = client.post("/register", json=_register_body())
    assert r.status_code == 200
    assert "image_png_base64" not in r.json()


def test_register_with_wrong_claim_reveals_no_image(client, monkeypatch):
    import app as app_module

    rec = FakeRecord()
    _fake_register_ok(monkeypatch, rec)
    other = app_module._claims.put(WID, "ee" * 32, "WRONG", ip="test").token
    r = client.post("/register", json=_register_body(claim=other))
    assert r.status_code == 200
    assert "image_png_base64" not in r.json()


def test_claim_withholds_image_until_the_id_is_on_chain(client, monkeypatch):
    import app as app_module

    token = app_module._claims.put(WID, FP, "MARKED_BYTES", ip="test").token
    monkeypatch.setattr("chain.lookup", lambda wid: None)
    r = client.get("/claim", params={"token": token})
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "not_registered"

    rec = FakeRecord()
    monkeypatch.setattr("chain.lookup", lambda wid: rec)
    r = client.get("/claim", params={"token": token})
    assert r.status_code == 200
    assert r.json()["image_png_base64"] == "MARKED_BYTES"
    # consumed: a second call cannot reveal it again
    assert client.get("/claim", params={"token": token}).status_code == 404


def test_claim_unknown_token_is_404(client):
    assert client.get("/claim", params={"token": "nope"}).status_code == 404


def test_mark_endpoint_never_returns_the_image_directly(client, monkeypatch):
    """A regression guard: even with a fake core.mark, /mark must only hand back a claim."""
    import app as app_module

    monkeypatch.setattr("core.mark", lambda data: {
        "watermark_id": WID, "fingerprint": FP, "width": 8, "height": 8, "strength": 1.0,
        "self_test": {"png": True, "jpeg70": True}, "image_png_base64": "SECRET_PIXELS"})
    r = client.post("/mark", files={"file": ("a.png", b"x", "image/png")})
    assert r.status_code == 200
    out = r.json()
    assert "image_png_base64" not in out
    assert out["claim"] and out["claim_expires_in"] > 0
    # the claim can still be redeemed once, after the record exists
    monkeypatch.setattr("chain.lookup", lambda wid: FakeRecord())
    revealed = client.get("/claim", params={"token": out["claim"]}).json()
    assert revealed["image_png_base64"] == "SECRET_PIXELS"
