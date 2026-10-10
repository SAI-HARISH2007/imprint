"""The fingerprint spec is a contract: pinned algorithm id plus fixed vectors.

Any independent reimplementation must reproduce these exact 64-hex strings from
the described recipe. They were cross-checked against imagehash 4.3.2's
``phash(hash_size=16)``, so existing on-chain records stay interpretable.
"""
import numpy as np
import pytest
from PIL import Image

import fingerprint as fp

# ---------------------------------------------------------------- fixtures
def pattern(w: int, h: int) -> Image.Image:
    """A deterministic colour pattern; no randomness, so the vectors are stable."""
    xs = np.arange(w)[None, :]
    ys = np.arange(h)[:, None]
    r = (xs * 7 + ys * 13) % 256
    g = (xs * 3 + ys * 5) % 256
    b = (xs ^ ys) % 256
    return Image.fromarray(np.stack([r, g, b], -1).astype("uint8"), "RGB")


# Fixed vectors for algorithm phash-dct-16x16-v1 on the installed library stack.
VECTORS = {
    (64, 64): "8ccf81112cff6607488e1afb0cce5efbfc40391123de7e0150ef55aaff08107b",
    (128, 96): "a40408fbe40408ff5eb4f0ff5c04b1ff8b1554ab11b6572b13e4ff914bc4aa8d",
    (37, 53): "863300046ebfd001173d11433ff9f0062ffe580a2775ad575aea7c2ba95faa55",
}


@pytest.mark.parametrize("size,expected", list(VECTORS.items()))
def test_pinned_vectors(size, expected):
    assert fp.compute(pattern(*size)) == expected


def test_horizontal_gradient_vector():
    g = Image.fromarray(np.tile(np.arange(256, dtype="uint8"), (256, 1)), "L").convert("RGB")
    assert fp.compute(g) == "8000000000000000000000000000000000000000000000000000000000000000"


def test_greyscale_luma_ignores_alpha_but_keeps_colour():
    # Two images with different colour but identical luma must hash the same.
    a = Image.new("RGB", (64, 64), (10, 20, 30))
    b = Image.new("RGBA", (64, 64), (10, 20, 30, 200))
    assert fp.compute(a) == fp.compute(b)


# ---------------------------------------------------------------- reference recipe
def reference_bits(img: Image.Image) -> int:
    """The documented recipe, written independently of fingerprint.py."""
    import scipy.fftpack

    g = img.convert("L").resize((64, 64), Image.Resampling.LANCZOS)
    px = np.asarray(g, dtype=np.float64)
    d = scipy.fftpack.dct(scipy.fftpack.dct(px, axis=0), axis=1)
    low = d[:16, :16]
    med = np.median(low)
    value = 0
    for bit in (low > med).reshape(-1):
        value = (value << 1) | int(bit)
    return value


@pytest.mark.parametrize("size", list(VECTORS))
def test_reference_recipe_matches(size):
    img = pattern(*size)
    assert reference_bits(img) == fp.compute_bits(img)


def test_matches_imagehash_implementation():
    imagehash = pytest.importorskip("imagehash")
    for size in VECTORS:
        img = pattern(*size)
        assert fp.compute(img) == str(imagehash.phash(img, hash_size=16))


# ---------------------------------------------------------------- encoding + distance
def test_hex_roundtrip_and_normalize():
    for hexstr in VECTORS.values():
        assert fp.to_hex(fp.from_hex(hexstr)) == hexstr
        assert fp.normalize("0x" + hexstr.upper()) == hexstr
        assert fp.from_hex("0x" + hexstr) == int(hexstr, 16)


def test_bit_length_and_hex_length():
    assert fp.BIT_LEN == 256 and fp.HEX_LEN == 64
    assert len(fp.compute(pattern(50, 50))) == 64


@pytest.mark.parametrize("bad", ["", "xyz", "0" * 63, "0" * 65, "g" * 64, 123, None])
def test_is_valid_rejects_bad(bad):
    assert fp.is_valid(bad) is False


def test_is_valid_accepts_good():
    assert fp.is_valid(VECTORS[(64, 64)]) is True
    assert fp.is_valid("0x" + VECTORS[(64, 64)]) is True


def test_distance_known_values():
    a = "00" * 32
    assert fp.distance(a, a) == 0
    assert fp.distance(a, "ff" * 32) == 256
    assert fp.distance(a, "00" * 31 + "03") == 2
    assert fp.distance(a, "00" * 31 + "01") == 1


def test_distance_is_symmetric_and_zero_iff_equal():
    a, b = VECTORS[(64, 64)], VECTORS[(128, 96)]
    assert fp.distance(a, b) == fp.distance(b, a) == 128
    assert fp.distance(a, a) == 0


def test_distance_agrees_with_imagehash():
    imagehash = pytest.importorskip("imagehash")
    a = fp.compute(pattern(64, 64))
    b = fp.compute(pattern(48, 72))
    ref = int(imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b))
    assert fp.distance(a, b) == ref
