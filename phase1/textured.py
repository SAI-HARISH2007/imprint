"""Busy, high-texture images (ruled paper, ink, sensor noise): does the mark survive, and does a higher strength help?"""
import secrets, sys, json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, str(Path(__file__).parent.parent / "service"))
import core
from stress import _jpeg

tm = core._tm(); n = core.payload_bits()

def notebook(seed, w=3024, h=4032):
    rng = np.random.default_rng(seed)
    base = Image.new("RGB", (w, h), (226, 222, 205))
    d = ImageDraw.Draw(base)
    for y in range(120, h, 62):                      # ruled lines
        d.line([(0, y), (w, y)], fill=(120, 140, 190), width=3)
    for _ in range(900):                             # ink strokes / handwriting-like
        x, y = rng.integers(100, w - 100), rng.integers(100, h - 100)
        pts = [(x + int(rng.normal(0, 40)) * i, y + int(rng.normal(0, 25)) * i // 2) for i in range(5)]
        d.line(pts, fill=(40, 40, 140), width=int(rng.integers(3, 8)))
    im = base.filter(ImageFilter.GaussianBlur(1.2))
    a = np.asarray(im).astype(np.float32) + rng.normal(0, 9, (h, w, 3))   # sensor noise
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

def psnr(a, b):
    mse = np.mean((np.asarray(a).astype(np.float32) - np.asarray(b).astype(np.float32)) ** 2)
    return 99.0 if mse == 0 else 10 * np.log10(255 ** 2 / mse)

out = {}
for strength in (1.0, 1.5, 2.0, 3.0):
    png = q90 = q70 = 0; ps = []
    N = 6
    for s in range(N):
        im = notebook(s)
        bits = "".join(secrets.choice("01") for _ in range(n))
        m = tm.encode(im, bits, MODE="binary", WM_STRENGTH=strength).convert("RGB")
        ps.append(psnr(im, m))
        def ok(x):
            sec, pres, _ = tm.decode(x, MODE="binary"); return bool(pres) and sec == bits
        png += ok(m); q90 += ok(_jpeg(m, 90)); q70 += ok(_jpeg(m, 70))
    out[str(strength)] = {"png": f"{png}/{N}", "jpeg90": f"{q90}/{N}", "jpeg70": f"{q70}/{N}", "psnr_db": round(float(np.mean(ps)), 1)}
    print(f"strength {strength}:  png {png}/{N}  jpeg q90 {q90}/{N}  jpeg q70 {q70}/{N}   PSNR {np.mean(ps):.1f} dB", flush=True)
json.dump(out, open("results/phase1c_textured.json", "w"), indent=2)
