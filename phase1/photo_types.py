"""Why did a real phone photo lose its mark? Try photo-like conditions on known-good images."""
import io, secrets, sys, json
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
sys.path.insert(0, str(Path(__file__).parent.parent / "service"))
import core
from stress import _jpeg, _scale

tm = core._tm(); n = core.payload_bits()
paths = sorted(Path("images").glob("photo_*.png"))[:10]

def dark(im, g=0.45):
    a = (np.asarray(im).astype(np.float32) / 255.0) ** (1/g) * 0.8
    noise = np.random.default_rng(1).normal(0, 4, a.shape)
    return Image.fromarray(np.clip(a * 255 + noise, 0, 255).astype(np.uint8))

def phone(im):  # 4032x3024 landscape
    return im.resize((4032, 3024), Image.LANCZOS)

VARIANTS = {
    "baseline 1024x768": lambda im: im,
    "portrait 768x1024": lambda im: im.rotate(90, expand=True),
    "phone 4032x3024": phone,
    "phone portrait 3024x4032": lambda im: phone(im).rotate(90, expand=True),
    "low light (dark+noise)": dark,
    "grayscale-ish paper (desaturated)": lambda im: ImageOps.grayscale(im).convert("RGB"),
}
out = {}
for name, fn in VARIANTS.items():
    ident = q90 = q70 = 0
    for p in paths:
        im = fn(Image.open(p).convert("RGB"))
        bits = "".join(secrets.choice("01") for _ in range(n))
        m = tm.encode(im, bits, MODE="binary").convert("RGB")
        def ok(x):
            s, pres, _ = tm.decode(x, MODE="binary"); return bool(pres) and s == bits
        ident += ok(m); q90 += ok(_jpeg(m, 90)); q70 += ok(_jpeg(m, 70))
    out[name] = {"png": f"{ident}/{len(paths)}", "jpeg90": f"{q90}/{len(paths)}", "jpeg70": f"{q70}/{len(paths)}"}
    print(f"{name:<36} png {ident}/{len(paths)}   jpeg q90 {q90}/{len(paths)}   jpeg q70 {q70}/{len(paths)}", flush=True)
json.dump(out, open("results/phase1c_photo_types.json", "w"), indent=2)
