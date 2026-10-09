"""Fast tests for the false-rejection investigation: recipe parity and helpers."""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "service"))

import fingerprint as fp  # noqa: E402
import investigate  # noqa: E402
from corpus import generate  # noqa: E402


def test_local_recipe_matches_published_fingerprint():
    for s in generate("calibration", 1):
        assert investigate.hashstr(investigate.coeffs(s.img)) == fp.compute(s.img)


def test_bits_are_256_and_output_deterministic():
    s = generate("heldout", 1)[0]
    a = investigate.bits(investigate.coeffs(s.img))
    b = investigate.bits(investigate.coeffs(s.img))
    assert a.shape == (256,)
    assert (a == b).all()


def test_distance_is_popcount():
    s = generate("heldout", 1)[0]
    c = investigate.coeffs(s.img)
    b = investigate.bits(c)
    flip = b.copy()
    flip[0] ^= 1
    flip[255] ^= 1
    d = int((b ^ flip).sum())
    assert d == 2