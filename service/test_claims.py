"""Claim store: the mechanism that keeps a marked image off the wire until its
ID is on chain. Pure and fast, no model or chain needed."""
import time

import claims

WID = "0x" + "ab" * 32
FP = "cd" * 32


def store(**kw):
    return claims.ClaimStore(ttl=kw.pop("ttl", 60), max_items=kw.pop("max_items", 100))


def test_put_get_roundtrip():
    s = store()
    c = s.put(WID, FP, "IMGDATA", ip="1.2.3.4")
    assert len(s) == 1
    got = s.get(c.token)
    assert got is not None and got.image_png_base64 == "IMGDATA"
    assert got.watermark_id == WID.lower() and got.fingerprint == FP


def test_get_unknown_is_none():
    s = store()
    assert s.get("nope") is None
    assert s.get("") is None


def test_take_requires_matching_id_and_fingerprint():
    s = store()
    c = s.put(WID, FP, "IMG")
    assert s.take(c.token, "0x" + "00" * 32, FP) is None  # wrong id
    assert s.take("wrong-token", WID, FP) is None
    assert s.get(c.token) is not None  # a mismatch does not burn the claim
    got = s.take(c.token, WID, FP)
    assert got is not None and got.image_png_base64 == "IMG"
    assert s.get(c.token) is None  # consumed


def test_take_accepts_0x_prefixed_fingerprint():
    s = store()
    c = s.put(WID, FP, "IMG")
    assert s.take(c.token, WID, "0x" + FP) is not None


def test_take_by_id_consumes_the_claims_own_image():
    s = store()
    c = s.put(WID, FP, "IMG")
    got = s.take_by_id(WID)
    assert got is not None and got.token == c.token
    assert s.get(c.token) is None


def test_expiry_drops_the_claim():
    s = claims.ClaimStore(ttl=0.05, max_items=10)
    c = s.put(WID, FP, "IMG")
    assert s.get(c.token) is not None
    time.sleep(0.08)
    assert s.get(c.token) is None
    assert len(s) == 0


def test_one_outstanding_claim_per_id():
    s = store()
    c1 = s.put(WID, FP, "IMG1")
    c2 = s.put(WID, FP, "IMG2")
    assert s.get(c1.token) is None  # replaced
    assert s.get(c2.token) is not None
    assert len(s) == 1


def test_store_is_bounded():
    s = claims.ClaimStore(ttl=999, max_items=5)
    tokens = [s.put("0x%064x" % i, FP, "IMG").token for i in range(20)]
    assert len(s) <= 5
    # the most recent survives
    assert s.get(tokens[-1]) is not None


def test_distinct_ids_keep_distinct_claims():
    s = store()
    a = s.put("0x" + "01" * 32, FP, "A")
    b = s.put("0x" + "02" * 32, FP, "B")
    assert s.get(a.token).image_png_base64 == "A"
    assert s.get(b.token).image_png_base64 == "B"
