"""Fast tests for the real-channel capture harness: manifest validation and offline check."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "service"))

import channels  # noqa: E402
from corpus import generate  # noqa: E402


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _sample(category="portraitish"):
    return next(s for s in generate("calibration", 1) if s.category == category).img


def _root(tmp_path):
    return tmp_path / "root"


def _make_entry(root, img, channel="whatsapp", registered_hash="0" * 64):
    sub = root / channel
    sub.mkdir(parents=True, exist_ok=True)
    p = sub / "img.png"
    img.save(p, format="PNG")
    return {"id": f"{channel}_1", "channel": channel, "file": f"{channel}/img.png",
            "captured_at": "2026-01-01T00:00:00Z", "notes": "test", "registered_hash": registered_hash}


def test_validate_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPRINT_CHANNEL_ROOT", str(_root(tmp_path)))
    entry = _make_entry(_root(tmp_path), _sample())
    m = _root(tmp_path) / "manifest.json"
    m.write_text(json.dumps([entry]))
    assert channels.validate(_Args(manifest=str(m))) == 0


def test_validate_rejects_bad_channel_and_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPRINT_CHANNEL_ROOT", str(_root(tmp_path)))
    entry = _make_entry(_root(tmp_path), _sample("shapes"))
    entry["channel"] = "fax"
    entry["file"] = "nope.png"
    m = _root(tmp_path) / "manifest.json"
    m.write_text(json.dumps([entry]))
    assert channels.validate(_Args(manifest=str(m))) == 1


def test_run_produces_verdict(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPRINT_CHANNEL_ROOT", str(_root(tmp_path)))
    entry = _make_entry(_root(tmp_path), _sample())
    m = _root(tmp_path) / "manifest.json"
    m.write_text(json.dumps([entry]))
    assert channels.run(_Args(manifest=str(m), out="real_check.json")) == 0
    data = json.loads((tmp_path / "results" / "real_check.json").read_text())
    assert data["n_images"] == 1
    row = data["rows"][0]
    assert len(row["fingerprint"]) == 64
    assert "registered_distance" in row
    assert row["verdict"] in ("verified", "likely", "different")