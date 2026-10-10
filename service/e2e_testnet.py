"""End to end against the live Monad testnet registry, in process, with a software passkey.

Registers one image (this writes a real record on testnet), then checks shared copies of it.
Run from service/:  python e2e_testnet.py [path-to-image]
"""
import base64
import io
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app import app
from softpasskey import SoftPasskey

path = Path(sys.argv[1] if len(sys.argv) > 1 else "../phase1/images/photo_00.png")
raw = path.read_bytes()

with TestClient(app) as client:
    t0 = time.time()
    m = client.post("/mark", files={"file": (path.name, raw, "image/png")}).json()
    print(f"mark: id={m['watermark_id'][:14]}...  ({time.time()-t0:.1f}s)")
    assert "image_png_base64" not in m, "the marked image must be withheld until the ID is on chain"
    assert m["claim"], "mark must return a claim token"

    pk = SoftPasskey()
    ch = client.get("/challenge", params={"watermark_id": m["watermark_id"], "fingerprint": "0x" + m["fingerprint"]}).json()["challenge"]
    body = {"watermark_id": m["watermark_id"], "fingerprint": "0x" + m["fingerprint"],
            "auth": pk.assert_challenge(ch), "qx": pk.qx, "qy": pk.qy, "claim": m["claim"]}
    r = client.post("/register", json=body)
    print("register:", r.status_code, {k: v for k, v in r.json().items() if k in ("tx_hash", "block", "gas_used", "gas_limit", "seconds", "signer", "detail")})
    assert r.status_code == 200, r.text
    # the marked image is revealed only now that the record is on chain
    marked = base64.b64decode(r.json()["image_png_base64"])

    # shared copies: each should land on "verified", or at worst "likely_match" if the mark was lost
    img = Image.open(io.BytesIO(marked))

    def jpeg_bytes(im, q):
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=q); return buf.getvalue()

    copies = {
        "JPEG q70": jpeg_bytes(img, 70),
        "resize 75% + JPEG q60": jpeg_bytes(img.resize((img.width * 3 // 4, img.height * 3 // 4)), 60),
        "resize 50% + JPEG q50": jpeg_bytes(img.resize((img.width // 2, img.height // 2)), 50),
    }
    for name, data in copies.items():
        v = client.post("/verify", files={"file": ("shared.jpg", data, "image/jpeg")}).json()
        print(f"verify ({name}): {v['verdict']}  distance={v['distance']}  mark={'yes' if v['watermark_present'] else 'no'}")
        assert v["verdict"] in ("verified", "likely_match"), v
    first = client.post("/verify", files={"file": ("shared.jpg", copies["JPEG q70"], "image/jpeg")}).json()
    print("   registration tx:", first["record"]["tx_url"])

    # squatting: re-mark the already registered image and try to register it again
    m2 = client.post("/mark", files={"file": ("again.png", marked, "image/png")}).json()
    pk2 = SoftPasskey()
    ch2 = client.get("/challenge", params={"watermark_id": m2["watermark_id"], "fingerprint": "0x" + m2["fingerprint"]}).json()["challenge"]
    r2 = client.post("/register", json={"watermark_id": m2["watermark_id"], "fingerprint": "0x" + m2["fingerprint"],
                                        "auth": pk2.assert_challenge(ch2), "qx": pk2.qx, "qy": pk2.qy})
    print("squat attempt:", r2.status_code, r2.json()["detail"]["error"] if r2.status_code == 409 else r2.text)
    assert r2.status_code == 409

    # stress table
    t0 = time.time()
    s = client.post("/stress", files={"file": ("marked.png", marked, "image/png")}).json()["results"]
    print(f"\nstress ({time.time()-t0:.1f}s)")
    for row in s:
        print(f"  {row['group']:<8} {row['label']:<34} {row['verdict']:<12} dist={row['distance']}  mark={'yes' if row['watermark_present'] else 'no'}")
    print("\nregistry count:", client.get("/records").json()["count"])
