"""Create the example images the website offers on the Check and Stress pages.

Registers one image on the live testnet registry with a script-held passkey stand-in, then writes:
  demo-1-marked.png       the registered original
  demo-1-shared.jpg       the same image halved and compressed
  demo-1-edited.png       the same image with a block of content pasted over it
  demo-2-unregistered.jpg a different image that is never registered
Each file is verified before it is kept, so the labels on the site are true.
Run from service/:  python make_demo.py
"""
import base64
import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import stress
from app import app
from softpasskey import SoftPasskey

ROOT = Path(__file__).parent.parent
OUT = ROOT / "web" / "public" / "demo"
OUT.mkdir(parents=True, exist_ok=True)
SRC_REGISTERED = ROOT / "phase1" / "images" / "photo_07.png"
SRC_OTHER = ROOT / "phase1" / "images" / "photo_11.png"


def post(client, path, name, data, mime):
    return client.post(path, files={"file": (name, data, mime)}).json()


def to_bytes(img, fmt, **kw):
    buf = io.BytesIO()
    img.save(buf, fmt, **kw)
    return buf.getvalue()


with TestClient(app) as client:
    raw = SRC_REGISTERED.read_bytes()
    m = client.post("/mark", files={"file": ("demo.png", raw, "image/png")}).json()

    pk = SoftPasskey("imprint-demo")
    ch = client.get("/challenge", params={"watermark_id": m["watermark_id"], "fingerprint": "0x" + m["fingerprint"]}).json()["challenge"]
    r = client.post("/register", json={"watermark_id": m["watermark_id"], "fingerprint": "0x" + m["fingerprint"],
                                       "auth": pk.assert_challenge(ch), "qx": pk.qx, "qy": pk.qy})
    assert r.status_code == 200, r.text
    print("registered:", r.json()["tx_hash"])
    marked_bytes = base64.b64decode(m["image_png_base64"])

    marked = Image.open(io.BytesIO(marked_bytes)).convert("RGB")
    (OUT / "demo-1-marked.png").write_bytes(marked_bytes)

    # a shared copy that is verified, not just likely
    shared = None
    for scale, q in [(0.5, 60), (0.5, 70), (0.6, 70), (0.75, 70)]:
        small = marked.resize((int(marked.width * scale), int(marked.height * scale)), Image.LANCZOS)
        data = to_bytes(small, "JPEG", quality=q)
        v = post(client, "/verify", "s.jpg", data, "image/jpeg")
        if v["verdict"] == "verified":
            shared = data
            print(f"shared copy: scale {scale}, q{q} -> verified, distance {v['distance']}")
            break
    assert shared, "no verified shared copy found"
    (OUT / "demo-1-shared.jpg").write_bytes(shared)

    # an edited copy that reads as altered
    edited = None
    for frac in (0.04, 0.06, 0.08, 0.05):
        img = stress._paste_patch(marked, frac)
        data = to_bytes(img, "PNG")
        v = post(client, "/verify", "e.png", data, "image/png")
        print(f"edit {frac:.0%}: {v['verdict']} distance {v['distance']}")
        if v["verdict"] == "altered":
            edited = data
            break
    assert edited, "no edit produced 'altered'"
    (OUT / "demo-1-edited.png").write_bytes(edited)

    other = Image.open(SRC_OTHER).convert("RGB")
    data = to_bytes(other, "JPEG", quality=85)
    v = post(client, "/verify", "u.jpg", data, "image/jpeg")
    assert v["verdict"] == "not_found", v["verdict"]
    (OUT / "demo-2-unregistered.jpg").write_bytes(data)
    print("unregistered: not_found")

for p in sorted(OUT.iterdir()):
    print(p.name, round(p.stat().st_size / 1024), "KB")
