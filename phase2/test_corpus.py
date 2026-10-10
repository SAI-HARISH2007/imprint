"""Fast tests for the phase 2 corpus: determinism, the leakage guard, and diversity."""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "service"))

import corpus  # noqa: E402
import fingerprint as fp  # noqa: E402


def test_generation_is_deterministic():
    a = corpus.generate("heldout", 2)
    b = corpus.generate("heldout", 2)
    assert [s.content_hash for s in a] == [s.content_hash for s in b]


def test_calibration_and_heldout_do_not_leak():
    cal = corpus.generate("calibration", 2)
    held = corpus.generate("heldout", 2)
    corpus.check_no_leakage(cal, held)  # raises LeakageError on any overlap


def test_leak_guard_actually_catches_overlap():
    cal = corpus.generate("calibration", 2)
    leaky = list(cal) + corpus.generate("heldout", 1)  # same content as calibration
    import pytest

    with pytest.raises(corpus.LeakageError):
        corpus.check_no_leakage(cal, leaky)


def test_all_categories_present_and_distinct():
    samples = corpus.generate("calibration", 1)
    assert {s.category for s in samples} == set(corpus.CATEGORIES)
    assert len({s.content_hash for s in samples}) == len(samples)


def test_same_category_images_are_distinct():
    for cat in corpus.CATEGORIES:
        samples = [s for s in corpus.generate("heldout", 3) if s.category == cat]
        assert len({s.content_hash for s in samples}) == len(samples)


def test_synthesized_fingerprints_are_not_identical():
    samples = corpus.generate("heldout", 2)
    fps = [fp.compute(s.img) for s in samples]
    for i in range(len(fps)):
        for j in range(i + 1, len(fps)):
            assert fp.distance(fps[i], fps[j]) > 0
