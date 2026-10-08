import base64
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import core
import verdict
from verdict import Record

IMG = Path(__file__).parent.parent / "phase1" / "images" / "photo_00.png"


def rec(wm_id, fp, signer="0xabc", ts=1):
    return Record(wm_id, fp, signer, ts)


# ---------- verdict logic (no model needed) ----------
FP_A = "0" * 64
FP_NEAR = "0" * 63 + "3"        # 2 bits away from FP_A
FP_FAR = "f" * 64               # 256 bits away


def test_verified_when_mark_found_and_content_close():
    r = rec("0x1", FP_A)
    out = verdict.decide(True, "0x1", FP_NEAR, r, [r])
    assert out["verdict"] == "verified" and out["distance"] == 2


def test_altered_when_mark_found_but_content_far():
    r = rec("0x1", FP_A)
    out = verdict.decide(True, "0x1", FP_FAR, r, [r])
    assert out["verdict"] == "altered"


def test_likely_match_when_mark_lost_but_looks_the_same():
    r = rec("0x1", FP_A)
    out = verdict.decide(False, None, FP_NEAR, None, [r])
    assert out["verdict"] == "likely_match"


def test_not_found_for_unrelated_image():
    r = rec("0x1", FP_A)
    out = verdict.decide(False, None, FP_FAR, None, [r])
    assert out["verdict"] == "not_found" and out["record"] is None


def test_not_found_notes_unregistered_mark():
    out = verdict.decide(True, "0x9", FP_FAR, None, [])
    assert out["verdict"] == "not_found" and "not in this registry" in out["message"]


def test_near_duplicate_blocks_squatting():
    r = rec("0x1", FP_A)
    assert verdict.find_near_duplicate(FP_NEAR, [r])[0] is r
    assert verdict.find_near_duplicate(FP_FAR, [r]) is None


# ---------- end to end with the real model ----------
needs_image = pytest.mark.skipif(not IMG.exists(), reason="run phase1/robustness.py first to fetch test images")


@needs_image
def test_mark_survives_jpeg_and_resize_and_bytes_do_not():
    client = TestClient(__import__("app").app)
    raw = IMG.read_bytes()
    r = client.post("/mark", files={"file": ("a.png", raw, "image/png")})
    assert r.status_code == 200
    m = r.json()
    marked = base64.b64decode(m["image_png_base64"])

    img = Image.open(io.BytesIO(marked))
    buf = io.BytesIO()
    img.resize((img.width // 2, img.height // 2)).save(buf, "JPEG", quality=60)
    shared = buf.getvalue()
    assert shared != marked

    c = client.post("/check", files={"file": ("b.jpg", shared, "image/jpeg")}).json()
    assert c["watermark_present"] and c["watermark_id"] == m["watermark_id"]
    assert core.distance(c["fingerprint"], m["fingerprint"]) <= verdict.T_MATCH


@needs_image
def test_unmarked_image_reads_as_no_watermark():
    client = TestClient(__import__("app").app)
    c = client.post("/check", files={"file": ("a.png", IMG.read_bytes(), "image/png")}).json()
    assert c["watermark_present"] is False and c["watermark_id"] is None


def test_garbage_upload_is_a_400():
    client = TestClient(__import__("app").app)
    r = client.post("/check", files={"file": ("x.txt", b"not an image", "text/plain")})
    assert r.status_code == 400
