"""Phase 1 follow-ups: harder transforms, the squatting (double-mark) case, and threshold separation."""
import json
import random
import statistics
from pathlib import Path

from PIL import Image, ImageOps
from trustmark import TrustMark

from robustness import IMG_DIR, OUT_DIR, TRANSFORMS, paste_edit, phash_bits

random.seed(11)
tm = TrustMark(verbose=False, model_type="Q", encoding_type=TrustMark.Encoding.BCH_5)
nbits = tm.schemaCapacity()
paths = sorted(IMG_DIR.glob("photo_*.png"))
imgs = [Image.open(p).convert("RGB") for p in paths]


def rbits():
    return "".join(random.choice("01") for _ in range(nbits))


hard = {
    "hflip": lambda im: ImageOps.mirror(im),
    "rotate_5deg": lambda im: im.rotate(5, expand=False, resample=Image.BICUBIC),
    "grayscale": lambda im: ImageOps.grayscale(im).convert("RGB"),
    "upscale_2x_then_q70": lambda im: TRANSFORMS["jpeg_q70"](im.resize((im.width * 2, im.height * 2), Image.LANCZOS), None),
}
hard_ok = {k: 0 for k in hard}
double = {"second_payload_wins": 0, "first_payload_survives": 0, "neither": 0}
dist_edit10, dist_edit25, dist_normal = [], [], []

for i, cover in enumerate(imgs):
    a = rbits()
    marked = tm.encode(cover, a, MODE="binary").convert("RGB")
    h0 = phash_bits(marked)
    for k, fn in hard.items():
        s, present, _ = tm.decode(fn(marked), MODE="binary")
        hard_ok[k] += int(bool(present) and s == a)
    # squatting: someone re-marks an already registered image with their own payload
    b = rbits()
    remarked = tm.encode(marked, b, MODE="binary").convert("RGB")
    s, present, _ = tm.decode(remarked, MODE="binary")
    if present and s == b:
        double["second_payload_wins"] += 1
    elif present and s == a:
        double["first_payload_survives"] += 1
    else:
        double["neither"] += 1
    dist_normal.append(int(h0 - phash_bits(remarked)))  # how close is the re-marked copy to the original
    donor = imgs[(i + 1) % len(imgs)]
    dist_edit10.append(int(h0 - phash_bits(paste_edit(marked, donor, 0.10))))
    dist_edit25.append(int(h0 - phash_bits(paste_edit(marked, donor, 0.25))))

n = len(imgs)
out = {
    "n_images": n,
    "hard_transform_decode_rate": {k: v / n for k, v in hard_ok.items()},
    "double_mark_outcome": double,
    "remarked_copy_phash_dist_to_original": {"median": statistics.median(dist_normal), "max": max(dist_normal)},
    "edit_paste_10pct_dist": {"min": min(dist_edit10), "median": statistics.median(dist_edit10)},
    "edit_paste_25pct_dist": {"min": min(dist_edit25), "median": statistics.median(dist_edit25)},
}
(OUT_DIR / "phase1_extra.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
