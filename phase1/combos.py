"""Phase 1b: combined transforms and large images (closer to a phone photo sent through a messenger)."""
import io, json, secrets, statistics, sys, urllib.request
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent.parent / "service"))
import core
from stress import _jpeg, _scale

tm = core._tm(); nbits = core.payload_bits()
IMG = Path(__file__).parent / "images_large"; IMG.mkdir(exist_ok=True)

def get(i, w, h, tag):
    p = IMG / f"{tag}_{i:02d}.png"
    if not p.exists():
        data = urllib.request.urlopen(f"https://picsum.photos/seed/imprintL{i}/{w}/{h}", timeout=60).read()
        Image.open(io.BytesIO(data)).convert("RGB").save(p)
    return Image.open(p).convert("RGB")

def to_long(img, n):
    s = n / max(img.size)
    return _scale(img, s) if s < 1 else img

COMBOS = {
    "resize50_q70": lambda im: _jpeg(_scale(im, .5), 70),
    "resize50_q50": lambda im: _jpeg(_scale(im, .5), 50),
    "resize25_q60": lambda im: _jpeg(_scale(im, .25), 60),
    "messenger_1600_q70": lambda im: _jpeg(to_long(im, 1600), 70),
    "messenger_1280_q60": lambda im: _jpeg(to_long(im, 1280), 60),
    "social_1080_q75": lambda im: _jpeg(to_long(im, 1080), 75),
}
out = {}
for tag, (w, h) in {"small_1024": (1024, 768), "large_3000": (3000, 2000)}.items():
    n = 12; res = {k: 0 for k in COMBOS}
    for i in range(n):
        im = get(i, w, h, tag)
        bits = "".join(secrets.choice("01") for _ in range(nbits))
        marked = tm.encode(im, bits, MODE="binary").convert("RGB")
        for k, fn in COMBOS.items():
            s, present, _ = tm.decode(fn(marked), MODE="binary")
            res[k] += int(bool(present) and s == bits)
    out[tag] = {k: f"{v}/{n}" for k, v in res.items()}
    print(tag, out[tag], flush=True)
json.dump(out, open("results/phase1b_combos.json", "w"), indent=2)
