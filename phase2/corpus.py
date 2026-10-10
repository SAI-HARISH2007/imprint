"""Deterministic, offline synthetic corpus for the phase 2 evaluation.

Why synthetic. The phase 1 sets are 24 calibration photos and 40 held-out photos
fetched from a stock source, with one disclosed overlap between them. That is too
few and too homogeneous to characterise *where* the method fails. This generator
produces an unbounded, fully reproducible, license-free corpus with a built-in
leakage guard: calibration and held-out images are drawn from disjoint seed
ranges, so a held-out image cannot be a transform of a calibration one, and a
content hash is checked to prove it.

Categories deliberately include hard cases for a DCT perceptual hash:
- ``gradient`` and ``lowcontrast``: few non-trivial low-frequency coefficients,
  so the median threshold that builds the hash is close to the data;
- ``symmetry``: near-mirror-symmetric content, where the hash is ambiguous.

This module has no network and no model dependency; ``evaluate.py`` adds the
watermark.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

# Disjoint seed banks: a calibration seed can never equal a held-out seed, which
# is the structural half of the leakage guard. The content hash is the proof half.
_SPLIT_SEED = {"calibration": 0, "heldout": 1_000_000}

CATEGORIES = (
    "gradient",
    "lowcontrast",
    "symmetry",
    "noise",
    "shapes",
    "texture",
    "portraitish",
)

DEFAULT_SIZE = (512, 512)


class LeakageError(AssertionError):
    """Raised when a calibration image also appears in the held-out set."""


@dataclass(frozen=True)
class Sample:
    name: str
    category: str
    split: str
    img: Image.Image
    content_hash: str


def _hash(img: Image.Image) -> str:
    return hashlib.sha256(f"{img.size}|".encode() + img.tobytes()).hexdigest()


def _img(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def _gradient(rng, w, h):
    ys, xs = np.mgrid[0:h, 0:w]
    r = xs / (w - 1)
    g = ys / (h - 1)
    b = (xs + ys) / (w + h - 2)
    phase = rng.uniform(0, np.pi)
    arr = np.stack([r, g, np.abs(np.sin(b * np.pi + phase))], axis=-1) * 220 + 20
    return _img(arr)


def _lowcontrast(rng, w, h):
    base = rng.uniform(90, 160, size=3)
    ys, xs = np.mgrid[0:h, 0:w]
    wave = np.sin(xs / rng.uniform(60, 160)) * np.cos(ys / rng.uniform(60, 160))
    arr = base[None, None, :] + wave[:, :, None] * rng.uniform(3, 9)
    return _img(arr)


def _symmetry(rng, w, h):
    half = np.zeros((h, w // 2, 3), np.float32)
    for _ in range(rng.integers(3, 7)):
        cx, cy = rng.integers(0, w // 2), rng.integers(0, h)
        rad = rng.integers(20, 90)
        col = rng.integers(30, 230, size=3).astype(np.float32)
        ys, xs = np.mgrid[0:h, 0:w // 2]
        m = (xs - cx) ** 2 + (ys - cy) ** 2 < rad * rad
        half[m] = col
    arr = np.concatenate([half, half[:, ::-1]], axis=1)
    return _img(arr + rng.normal(0, 4, arr.shape))


def _noise(rng, w, h):
    arr = 128 + rng.normal(0, rng.uniform(25, 55), (h, w, 3))
    return _img(arr)


def _shapes(rng, w, h):
    bg = rng.integers(0, 60, size=3)
    img = Image.new("RGB", (w, h), tuple(int(c) for c in bg))
    d = ImageDraw.Draw(img)
    for _ in range(rng.integers(4, 9)):
        x0, y0 = rng.integers(0, w), rng.integers(0, h)
        x1, y1 = x0 + rng.integers(40, 200), y0 + rng.integers(40, 200)
        col = tuple(int(c) for c in rng.integers(40, 256, size=3))
        if rng.random() < 0.5:
            d.ellipse([x0, y0, x1, y1], fill=col)
        else:
            d.rectangle([x0, y0, x1, y1], fill=col)
    return img


def _texture(rng, w, h):
    ys, xs = np.mgrid[0:h, 0:w]
    period = rng.uniform(6, 28)
    ang = rng.uniform(0, np.pi)
    coord = xs * np.cos(ang) + ys * np.sin(ang)
    wave = np.sin(2 * np.pi * coord / period)
    col = rng.integers(60, 200, size=3)
    arr = 128 + wave[:, :, None] * col[None, None, :] / 3
    return _img(arr)


def _portraitish(rng, w, h):
    ys, xs = np.mgrid[0:h, 0:w]
    warm = np.stack([xs / (w - 1), ys / (h - 1), 0.4 + 0.2 * np.ones_like(xs)], axis=-1)
    arr = warm * 180 + 40
    cx, cy = w * rng.uniform(0.3, 0.7), h * rng.uniform(0.3, 0.7)
    for rad, tone in ((0.18, (0.95, 0.8, 0.7)), (0.10, (0.2, 0.15, 0.12))):
        m = (xs - cx) ** 2 + (ys - cy) ** 2 < (rad * w) ** 2
        arr[m] = np.array(tone) * 255
    return _img(arr + rng.normal(0, 5, arr.shape))


_GEN = {
    "gradient": _gradient,
    "lowcontrast": _lowcontrast,
    "symmetry": _symmetry,
    "noise": _noise,
    "shapes": _shapes,
    "texture": _texture,
    "portraitish": _portraitish,
}


def generate(split: str, per_category: int, size=DEFAULT_SIZE) -> list[Sample]:
    """Deterministic samples for a split. Same args -> identical images, always."""
    if split not in _SPLIT_SEED:
        raise ValueError(f"unknown split {split!r}")
    w, h = size
    out: list[Sample] = []
    for ci, cat in enumerate(CATEGORIES):
        for i in range(per_category):
            seed = _SPLIT_SEED[split] + ci * 10_000 + i
            rng = np.random.default_rng(seed)
            img = _GEN[cat](rng, w, h)
            out.append(Sample(f"{split}_{cat}_{i:02d}", cat, split, img, _hash(img)))
    return out


def check_no_leakage(calibration: list[Sample], heldout: list[Sample]) -> None:
    """Assert the held-out set shares no image content with the calibration set.

    This is the leakage guard the phase 1 evaluation lacked. It fails loudly
    rather than silently inflating held-out numbers.
    """
    cal = {s.content_hash for s in calibration}
    held = {s.content_hash for s in heldout}
    dup = cal & held
    if dup:
        raise LeakageError(f"{len(dup)} image(s) appear in both splits: {sorted(dup)[:3]}")
    for name, group in (("calibration", calibration), ("heldout", heldout)):
        hashes = [s.content_hash for s in group]
        if len(set(hashes)) != len(hashes):
            raise LeakageError(f"{name} contains duplicate image content")


if __name__ == "__main__":
    cal = generate("calibration", 2)
    held = generate("heldout", 2)
    check_no_leakage(cal, held)
    print(f"calibration: {len(cal)}  heldout: {len(held)}  leak guard: OK")
    for cat in CATEGORIES:
        print(f"  {cat:<12} first={next(s.name for s in cal if s.category == cat)}")
