"""Canonical Imprint fingerprint: a 256-bit DCT perceptual hash (pHash).

This module is the single source of truth for how a fingerprint is computed.
The service, the standalone verifier and the test vectors all use it, so a
fingerprint recorded on Monad under version 1 can be reproduced by anyone.

Specification (algorithm id ``phash-dct-16x16-v1``)
---------------------------------------------------
1. Colour: convert the image to 8-bit grayscale with the ITU-R BT.601 luma
   transform (Pillow ``Image.convert("L")``).
2. Resize: resize to exactly 64x64 pixels with Lanczos resampling, ignoring
   aspect ratio (Pillow ``Image.Resampling.LANCZOS``).
3. DCT: treat the 64x64 grayscale plane as a float64 matrix and apply a
   type-II discrete cosine transform on axis 0 and then axis 1
   (``scipy.fftpack.dct`` with default ``type=2, norm=None``).
4. Low frequencies: keep the top-left 16x16 block of coefficients (the DC
   term is included).
5. Median: compute the median of those 256 coefficients.
6. Bits: emit a 1 where a coefficient is strictly greater than the median,
   else 0, scanning row by row (left to right, top to bottom).
7. Encoding: the 256 bits form a big-endian integer; render it as 64 lowercase
   hex characters, zero padded (the form stored on chain as ``bytes32``).

Bit order
---------
The first bit emitted (position 0) is the most significant bit of the integer
and the most significant nibble of the hex string. ``int(hex, 16)`` and the
256-bit on-chain word therefore share one ordering.

Hamming distance
----------------
``distance`` is the number of differing bits between two fingerprints, i.e.
the population count of the XOR of their 256-bit integers. This is a true
metric and is what the contract's ``hammingDistance`` view computes on chain.

Reproducibility limits
----------------------
Bit-for-bit equality is guaranteed only when the same numeric libraries are
used. The pinned versions (see ``requirements.txt``) and the test vectors in
``test_fingerprint.py`` are the contract for version 1. Coefficient values
that fall exactly on the median can flip a bit across BLAS/FFT builds; in
practice this is rare and would change the distance by one or two bits, well
inside the match thresholds.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

VERSION = 1
ALGORITHM = "phash-dct-16x16-v1"
HASH_SIZE = 16
HIGHFREQ_FACTOR = 4
IMAGE_SIZE = HASH_SIZE * HIGHFREQ_FACTOR  # 64
BIT_LEN = HASH_SIZE * HASH_SIZE  # 256
HEX_LEN = BIT_LEN // 4  # 64

_HEX = set("0123456789abcdef")


def compute_bits(img: Image.Image) -> int:
    """The 256-bit fingerprint of a PIL image as a big-endian integer."""
    import scipy.fftpack

    gray = img.convert("L").resize((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray, dtype=np.float64)
    dct = scipy.fftpack.dct(scipy.fftpack.dct(pixels, axis=0), axis=1)
    low = dct[:HASH_SIZE, :HASH_SIZE]
    median = np.median(low)
    bits = (low > median).reshape(-1)  # row-major, MSB first
    value = 0
    for b in bits:
        value = (value << 1) | int(b)
    return value


def to_hex(value: int) -> str:
    """A 256-bit integer -> 64 lowercase hex characters, no 0x prefix."""
    return f"{value & ((1 << BIT_LEN) - 1):0{HEX_LEN}x}"


def from_hex(fingerprint: str) -> int:
    """64 hex characters (with or without 0x) -> the 256-bit integer."""
    return int(normalize(fingerprint), 16)


def normalize(fingerprint: str) -> str:
    """Return the canonical 64-char lowercase hex form, or raise ValueError."""
    if not isinstance(fingerprint, str):
        raise ValueError("fingerprint must be a string")
    h = fingerprint[2:] if fingerprint[:2].lower() == "0x" else fingerprint
    h = h.lower()
    if len(h) != HEX_LEN or any(c not in _HEX for c in h):
        raise ValueError(f"fingerprint must be {HEX_LEN} hex characters")
    return h


def is_valid(fingerprint: object) -> bool:
    try:
        normalize(fingerprint)  # type: ignore[arg-type]
        return True
    except (ValueError, TypeError):
        return False


def compute(img: Image.Image) -> str:
    """The canonical 64-char hex fingerprint of a PIL image."""
    return to_hex(compute_bits(img))


def distance(a: str, b: str) -> int:
    """Hamming distance between two fingerprints (0..256)."""
    return bin(from_hex(a) ^ from_hex(b)).count("1")


def popcount(value: int) -> int:
    return bin(value & ((1 << BIT_LEN) - 1)).count("1")
