"""Standalone verifier: decides from the image and the chain only, never the
server. Uses a fake registry reader so no network is needed."""
import numpy as np
import pytest
from PIL import Image

import fingerprint as fp
import imprint_verify as iv
from verdict import T_MATCH, T_NEAR, Record

WID = "0x" + "11" * 32
WID2 = "0x" + "22" * 32


def pattern(w=64, h=64):
    xs = np.arange(w)[None, :]
    ys = np.arange(h)[:, None]
    b = (xs ^ ys) % 256
    return Image.fromarray(np.stack([(xs * 3) % 256 + 0 * ys, (ys * 5) % 256 + 0 * xs, b], -1).astype("uint8"), "RGB")


def flip(hexstr, n):
    v = fp.from_hex(hexstr)
    for i in range(n):
        v ^= 1 << i
    return fp.to_hex(v)


class FakeReader:
    def __init__(self, records):
        self._records = records

    def record(self, wid):
        return next((r for r in self._records if r.watermark_id.lower() == wid.lower()), None)

    def records(self, limit):
        return self._records[:limit]


@pytest.fixture()
def image_file(tmp_path):
    p = tmp_path / "img.png"
    pattern().save(p)
    return str(p)


def base_fp():
    return fp.compute(pattern())


def test_fingerprint_image_matches_spec(image_file):
    assert iv.fingerprint_image(image_file) == base_fp()


def test_verified_for_close_named_record(image_file):
    base = base_fp()
    rec = Record(WID, flip(base, 3), "0xalice", 10, block=1)
    out = iv.verify_image(image_file, watermark_id=WID, reader=FakeReader([rec]))
    assert out["status"] == "verified" and out["distance"] == 3
    assert out["assurance"] == "content-only" and out["algorithm"] == fp.ALGORITHM


def test_altered_for_near_but_changed(image_file):
    base = base_fp()
    d = (T_MATCH + T_NEAR) // 2
    rec = Record(WID, flip(base, d), "0xalice", 10, block=1)
    out = iv.verify_image(image_file, watermark_id=WID, reader=FakeReader([rec]))
    assert out["status"] == "altered" and out["distance"] == d


def test_not_found_when_content_far(image_file):
    rec = Record(WID, flip(base_fp(), T_NEAR + 20), "0xalice", 10, block=1)
    out = iv.verify_image(image_file, watermark_id=WID, reader=FakeReader([rec]))
    assert out["status"] == "not_found"


def test_not_found_for_unknown_id(image_file):
    out = iv.verify_image(image_file, watermark_id=WID, reader=FakeReader([]))
    assert out["status"] == "not_found"


def test_scan_finds_close_record_as_likely_match(image_file):
    base = base_fp()
    rec = Record(WID, flip(base, 2), "0xalice", 10, block=1)
    out = iv.verify_image(image_file, scan=True, reader=FakeReader([rec]))
    assert out["status"] == "likely_match" and out["method"] == "scan"


def test_scan_reports_not_found_for_empty_registry(image_file):
    out = iv.verify_image(image_file, scan=True, reader=FakeReader([]))
    assert out["status"] == "not_found"


def test_scan_with_no_target_is_error(image_file):
    out = iv.verify_image(image_file, reader=FakeReader([Record(WID, base_fp(), "0xa", 1, block=1)]))
    assert out["status"] == "error"


def test_dispute_when_earlier_lookalike_exists(image_file):
    base = base_fp()
    earlier = Record(WID2, flip(base, 5), "0xmallory", 5, block=1)  # within T_DUP, other signer, earlier
    named = Record(WID, base, "0xalice", 10, block=2)
    out = iv.verify_image(image_file, watermark_id=WID, reader=FakeReader([earlier, named]))
    assert out["status"] == "disputed" and out["earlier"]["watermark_id"] == WID2


def test_own_earlier_registration_is_not_a_dispute(image_file):
    base = base_fp()
    earlier = Record(WID2, flip(base, 5), "0xalice", 5, block=1)  # same signer
    named = Record(WID, base, "0xalice", 10, block=2)
    out = iv.verify_image(image_file, watermark_id=WID, reader=FakeReader([earlier, named]))
    assert out["status"] == "verified"


def test_unsupported_algorithm_version(image_file):
    out = iv.verify_image(image_file, watermark_id=WID, reader=FakeReader([]), algo="phash-8x8-v0")
    assert out["status"] == "unsupported_version"


def test_error_on_unreadable_image(tmp_path):
    p = tmp_path / "not.png"
    p.write_text("nope")
    out = iv.verify_image(str(p), watermark_id=WID, reader=FakeReader([]))
    assert out["status"] == "error"


def test_error_without_reader(image_file):
    out = iv.verify_image(image_file, watermark_id=WID, reader=None)
    assert out["status"] == "error"


def test_reader_error_is_reported(image_file):
    class Boom:
        def record(self, wid):
            raise RuntimeError("rpc down")

        def records(self, limit):
            raise RuntimeError("rpc down")

    out = iv.verify_image(image_file, watermark_id=WID, reader=Boom())
    assert out["status"] == "error" and "rpc down" in out["message"]
