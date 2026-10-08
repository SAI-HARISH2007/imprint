"""The stress panel: damage a registered image in many ways and verify each result.

Groups:
  sharing  ordinary things platforms do to images
  edit     changes to the content
  attack   deliberate attempts to defeat the system
"""
import base64
import hashlib
import io

import numpy as np
from PIL import Image, ImageEnhance

import chain
import core
import verdict


def _jpeg(img, q):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=q)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _scale(img, f):
    return img.resize((max(1, int(img.width * f)), max(1, int(img.height * f))), Image.LANCZOS)


def _crop(img, frac):
    dx, dy = int(img.width * frac / 2), int(img.height * frac / 2)
    return img.crop((dx, dy, img.width - dx, img.height - dy))


def _messenger(img):
    s = min(1.0, 1600 / max(img.size))
    return _jpeg(_scale(img, s) if s < 1 else img, 70)


def _screenshot_like(img):
    out = np.asarray(_scale(img, 0.83)).astype(np.float32) / 255.0
    out = np.clip(out ** 1.08, 0, 1)
    return _jpeg(Image.fromarray((out * 255).astype(np.uint8)), 85)


def _paste_patch(img, frac):
    """Clone-stamp: cover a block with a flipped piece of the same picture."""
    bw, bh = int(img.width * frac ** 0.5), int(img.height * frac ** 0.5)
    patch = img.transpose(Image.FLIP_LEFT_RIGHT).resize((bw, bh))
    out = img.copy()
    out.paste(patch, (img.width // 3, img.height // 3))
    return out


def synthetic_donor(size, seed=5):
    """A smooth, unrelated picture, used when no other image is supplied."""
    rng = np.random.default_rng(seed)
    small = rng.random((9, 12, 3)).astype(np.float32)
    big = Image.fromarray((small * 255).astype(np.uint8)).resize(size, Image.BICUBIC)
    noise = rng.normal(0, 6, (size[1], size[0], 3))
    return Image.fromarray(np.clip(np.asarray(big) + noise, 0, 255).astype(np.uint8))


def _remove_mark(img):
    with core.TM_LOCK:
        return core._tm().remove_watermark(img).convert("RGB")


def _transplant(img, donor):
    """Estimate the mark as (marked - cleaned) and add it to a different picture."""
    with core.TM_LOCK:
        clean = core._tm().remove_watermark(img).convert("RGB")
    res = np.asarray(img).astype(np.float32) - np.asarray(clean.resize(img.size)).astype(np.float32)
    target = np.asarray(donor.resize(img.size)).astype(np.float32)
    return Image.fromarray(np.clip(target + res, 0, 255).astype(np.uint8))


# (key, label, group, function(img, donor))
CASES = [
    ("jpeg_q90", "JPEG quality 90", "sharing", lambda im, d: _jpeg(im, 90)),
    ("jpeg_q70", "JPEG quality 70", "sharing", lambda im, d: _jpeg(im, 70)),
    ("jpeg_q50", "JPEG quality 50", "sharing", lambda im, d: _jpeg(im, 50)),
    ("jpeg_q20", "JPEG quality 20", "sharing", lambda im, d: _jpeg(im, 20)),
    ("resize_50", "Resized to 50%", "sharing", lambda im, d: _scale(im, 0.5)),
    ("messenger", "Messenger-style recompress", "sharing", lambda im, d: _messenger(im)),
    ("screenshot", "Screenshot-like rescale", "sharing", lambda im, d: _screenshot_like(im)),
    ("brightness", "Brightness +15%", "sharing", lambda im, d: ImageEnhance.Brightness(im).enhance(1.15)),
    ("crop_5", "Cropped 5%", "edit", lambda im, d: _crop(im, 0.05)),
    ("crop_15", "Cropped 15%", "edit", lambda im, d: _crop(im, 0.15)),
    ("patch_10", "Content pasted over 10%", "edit", lambda im, d: _paste_patch(im, 0.10)),
    ("patch_25", "Content pasted over 25%", "edit", lambda im, d: _paste_patch(im, 0.25)),
    ("remove_mark", "Watermark removed", "attack", lambda im, d: _remove_mark(im)),
    ("transplant", "Mark copied onto another image", "attack", lambda im, d: _transplant(im, d)),
    ("unrelated", "A different image entirely", "attack", lambda im, d: d.resize(im.size)),
]


def _thumb(img):
    t = img.copy()
    t.thumbnail((160, 120))
    buf = io.BytesIO()
    t.save(buf, "JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _to_png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def run(marked_bytes: bytes, donor_bytes: bytes | None = None) -> list[dict]:
    img = core.load_image(marked_bytes)
    donor = core.load_image(donor_bytes) if donor_bytes else synthetic_donor(img.size)
    records = chain.all_records()
    original_digest = hashlib.sha256(marked_bytes).hexdigest()
    out = []
    for key, label, group, fn in CASES:
        damaged = fn(img, donor)
        raw = _to_png_bytes(damaged)
        seen = core.read(raw)
        rec = chain.lookup(seen["watermark_id"]) if seen["watermark_present"] else None
        v = verdict.decide(seen["watermark_present"], seen["watermark_id"], seen["fingerprint"], rec, records)
        out.append({
            "key": key, "label": label, "group": group,
            "verdict": v["verdict"], "distance": v["distance"],
            "watermark_present": seen["watermark_present"],
            "file_hash_matches": hashlib.sha256(raw).hexdigest() == original_digest,
            "thumb": _thumb(damaged),
        })
    return out
