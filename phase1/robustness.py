"""Imprint phase 1: does an invisible watermark survive ordinary sharing?

Marks each test image with TrustMark, damages it in realistic ways, then checks
(a) whether the watermark payload still decodes exactly and
(b) how far the perceptual hash drifts from the marked original.

A file-byte hash is included as the baseline that should fail on every transform.
Run:  python robustness.py [--images N]
"""
import argparse
import hashlib
import io
import json
import random
import statistics
import sys
import urllib.request
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from trustmark import TrustMark

HERE = Path(__file__).parent
IMG_DIR = HERE / "images"
OUT_DIR = HERE / "results"
OUT_DIR.mkdir(exist_ok=True)
IMG_DIR.mkdir(exist_ok=True)

# Transforms that count as "ordinary sharing". The gate is decided on these.
NORMAL = {
    "jpeg_q90", "jpeg_q70", "jpeg_q50", "resize_75", "resize_50", "messenger",
}


def fetch_images(n: int) -> list[Path]:
    paths = []
    for i in range(n):
        p = IMG_DIR / f"photo_{i:02d}.png"
        if not p.exists():
            url = f"https://picsum.photos/seed/imprint{i}/1024/768"
            try:
                data = urllib.request.urlopen(url, timeout=30).read()
                Image.open(io.BytesIO(data)).convert("RGB").save(p)
            except Exception as e:  # keep going with whatever we got
                print(f"download failed for {url}: {e}", file=sys.stderr)
                continue
        paths.append(p)
    return paths


def jpeg(img: Image.Image, q: int) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=q)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def resize_frac(img: Image.Image, f: float) -> Image.Image:
    w, h = img.size
    return img.resize((max(1, int(w * f)), max(1, int(h * f))), Image.LANCZOS)


def crop_center(img: Image.Image, frac_removed: float) -> Image.Image:
    w, h = img.size
    dx, dy = int(w * frac_removed / 2), int(h * frac_removed / 2)
    return img.crop((dx, dy, w - dx, h - dy))


def messenger(img: Image.Image) -> Image.Image:
    """Roughly what chat apps do: cap the long side near 1600px, recompress to JPEG ~q70."""
    w, h = img.size
    scale = min(1.0, 1600 / max(w, h))
    out = resize_frac(img, scale) if scale < 1 else img
    return jpeg(out, 70)


def screenshot_like(img: Image.Image) -> Image.Image:
    """Rescale off-grid, nudge gamma, recompress: a crude stand-in for a screenshot."""
    out = resize_frac(img, 0.83)
    arr = np.asarray(out).astype(np.float32) / 255.0
    arr = np.clip(arr ** 1.08, 0, 1)
    out = Image.fromarray((arr * 255).astype(np.uint8))
    return jpeg(out, 85)


def paste_edit(img: Image.Image, donor: Image.Image, frac: float) -> Image.Image:
    """Malicious-ish edit: replace a block of the image with content from another picture."""
    w, h = img.size
    bw, bh = int(w * frac ** 0.5), int(h * frac ** 0.5)
    x0, y0 = w // 3, h // 3
    patch = donor.resize((bw, bh))
    out = img.copy()
    out.paste(patch, (x0, y0))
    return out


TRANSFORMS = {
    "identity": lambda im, d: im,
    "png_to_jpeg_q95": lambda im, d: jpeg(im, 95),
    "jpeg_q90": lambda im, d: jpeg(im, 90),
    "jpeg_q70": lambda im, d: jpeg(im, 70),
    "jpeg_q50": lambda im, d: jpeg(im, 50),
    "jpeg_q30": lambda im, d: jpeg(im, 30),
    "jpeg_q20": lambda im, d: jpeg(im, 20),
    "resize_75": lambda im, d: resize_frac(im, 0.75),
    "resize_50": lambda im, d: resize_frac(im, 0.50),
    "resize_25": lambda im, d: resize_frac(im, 0.25),
    "messenger": lambda im, d: messenger(im),
    "screenshot_like": lambda im, d: screenshot_like(im),
    "crop_5": lambda im, d: crop_center(im, 0.05),
    "crop_15": lambda im, d: crop_center(im, 0.15),
    "crop_30": lambda im, d: crop_center(im, 0.30),
    "brightness_p15": lambda im, d: ImageEnhance.Brightness(im).enhance(1.15),
    "brightness_m15": lambda im, d: ImageEnhance.Brightness(im).enhance(0.85),
    "contrast_p15": lambda im, d: ImageEnhance.Contrast(im).enhance(1.15),
    "blur_light": lambda im, d: im.filter(ImageFilter.GaussianBlur(1.0)),
    "edit_paste_10pct": lambda im, d: paste_edit(im, d, 0.10),
    "edit_paste_25pct": lambda im, d: paste_edit(im, d, 0.25),
}


def phash_bits(img: Image.Image) -> imagehash.ImageHash:
    return imagehash.phash(img, hash_size=16)  # 256-bit, closer to what PDQ gives


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", type=int, default=24)
    ap.add_argument("--model", default="Q")
    args = ap.parse_args()

    random.seed(7)
    paths = fetch_images(args.images)
    if len(paths) < 6:
        sys.exit("need at least 6 images, check network")

    tm = TrustMark(verbose=False, model_type=args.model, encoding_type=TrustMark.Encoding.BCH_5)
    nbits = tm.schemaCapacity()
    print(f"TrustMark model={args.model}, payload bits={nbits}, images={len(paths)}")

    imgs = [Image.open(p).convert("RGB") for p in paths]
    rows = []  # one row per (image, transform)
    marked_hashes = []

    for idx, (p, cover) in enumerate(zip(paths, imgs)):
        payload = "".join(random.choice("01") for _ in range(nbits))
        marked = tm.encode(cover, payload, MODE="binary").convert("RGB")
        base_hash = phash_bits(marked)
        marked_hashes.append(base_hash)
        base_bytes = hashlib.sha256(marked.tobytes()).hexdigest()
        donor = imgs[(idx + 1) % len(imgs)]

        for name, fn in TRANSFORMS.items():
            out = fn(marked, donor)
            try:
                secret, present, _ = tm.decode(out, MODE="binary")
            except Exception:
                secret, present = "", False
            ok = bool(present) and secret == payload
            dist = base_hash - phash_bits(out)
            same_bytes = hashlib.sha256(out.tobytes()).hexdigest() == base_bytes
            rows.append({
                "image": p.name, "transform": name, "decoded_exact": ok,
                "watermark_present": bool(present), "phash_dist": int(dist),
                "bytes_identical": same_bytes,
            })
        print(f"  done {p.name}")

    # Negative set: distance between unrelated marked images, and false watermark reads
    neg = [int(a - b) for i, a in enumerate(marked_hashes) for j, b in enumerate(marked_hashes) if i < j]
    unmarked_false = 0
    for cover in imgs:
        try:
            _, present, _ = tm.decode(cover, MODE="binary")
        except Exception:
            present = False
        unmarked_false += int(bool(present))

    # Summary
    by_t = {}
    for r in rows:
        by_t.setdefault(r["transform"], []).append(r)
    summary = {}
    for name, rs in by_t.items():
        summary[name] = {
            "decode_rate": sum(r["decoded_exact"] for r in rs) / len(rs),
            "median_phash_dist": statistics.median(r["phash_dist"] for r in rs),
            "max_phash_dist": max(r["phash_dist"] for r in rs),
            "byte_hash_survives": sum(r["bytes_identical"] for r in rs) / len(rs),
        }
    normal_rate = statistics.mean(summary[t]["decode_rate"] for t in NORMAL)

    result = {
        "model": args.model, "payload_bits": nbits, "n_images": len(paths),
        "summary": summary, "normal_sharing_mean_decode_rate": normal_rate,
        "unrelated_phash_dist": {
            "min": min(neg), "median": statistics.median(neg), "n_pairs": len(neg),
        },
        "false_watermark_on_unmarked": f"{unmarked_false}/{len(imgs)}",
    }
    (OUT_DIR / f"phase1_{args.model}.json").write_text(json.dumps(result, indent=2))

    print("\ntransform            decode  med_dist  max_dist  bytehash")
    for name, s in summary.items():
        print(f"{name:<20} {s['decode_rate']:>5.0%}  {s['median_phash_dist']:>8}  {s['max_phash_dist']:>8}  {s['byte_hash_survives']:>6.0%}")
    print(f"\nNormal-sharing mean decode rate: {normal_rate:.0%}  (gate: >= 70%)")
    print(f"Unrelated image pairs, 256-bit pHash distance: min {min(neg)}, median {statistics.median(neg)}")
    print(f"False watermark reads on unmarked originals: {unmarked_false}/{len(imgs)}")


if __name__ == "__main__":
    main()
