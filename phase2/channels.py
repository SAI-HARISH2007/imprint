"""Harness + protocol for real-world channel captures (WhatsApp/Telegram/screenshots/AI).

This suite does NOT generate data: real transfers and real phone screenshots and a
large held-out AI set must be created by people with phones, apps and models.
What this module commits is the *protocol*: a manifest schema, validation, an
offline check that runs the published fingerprint recipe on whatever is captured,
and summarisation. Captured images themselves stay out of git (see .gitignore,
phase2/real). Anyone can run:

    python channels.py init                      # create the capture directory skeleton
    # ... place images in phase2/real/<channel>/ and edit phase2/real/manifest.json ...
    python channels.py validate --manifest phase2/real/manifest.json
    python channels.py run --manifest phase2/real/manifest.json --out results/real_check.json
    python channels.py summarize --out results/real_check.json
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "service"))

import fingerprint as fp  # noqa: E402

CHANNELS = ("whatsapp", "telegram", "screenshot", "ai")
REQUIRED_KEYS = ("id", "channel", "file", "captured_at", "notes")


def root_path():
    return Path(os.getenv("IMPRINT_CHANNEL_ROOT", str(HERE / "real")))
T_MATCH = 16
T_NEAR = 24
T_DUP = 10


def _read_manifest(path):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, list):
        raise ValueError("manifest must be a JSON array of entries")
    return data


def _image_hash(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def check_entry_fingerprint(entry, root):
    """Offline: fingerprint the captured image and compare with the registration if given."""
    import PIL.Image  # local import keeps CLI startup fast

    p = (root / entry["file"]).resolve()
    img = PIL.Image.open(p)
    fh = fp.compute(img)
    out = {"id": entry["id"], "channel": entry["channel"], "file": str(entry["file"]),
           "sha256": _image_hash(p), "fingerprint": fh}
    rh = entry.get("registered_hash")
    if rh:
        a = int(fh, 16)
        b = int(rh, 16)
        d = (a ^ b).bit_count()
        out["registered_distance"] = d
        out["verdict"] = ("verified" if d <= T_MATCH
                          else ("likely" if d <= T_NEAR else "different"))
    out["notes"] = entry.get("notes", "")
    return out


def init(args) -> int:
    root = root_path()
    for ch in CHANNELS:
        (root / ch).mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(
        "Place captured images here, one file per manifest entry. This directory is "
        "git-ignored: the protocol (manifest schema + channels.py) is the artefact, "
        "the captures stay local. See docs/real-world-testing.md for the capture protocol.\n"
    )
    if not (root / "manifest.json").exists():
        (root / "manifest.json").write_text("[]\n")
    print("initialised", root)
    return 0


def validate(args) -> int:
    entries = _read_manifest(args.manifest)
    ids, errors = set(), []
    for i, e in enumerate(entries):
        for k in REQUIRED_KEYS:
            if k not in e:
                errors.append(f"entry {i}: missing '{k}'")
        if e.get("id") in ids:
            errors.append(f"entry {i}: duplicate id '{e.get('id')}'")
        if e.get("channel") not in CHANNELS:
            errors.append(f"entry {i}: bad channel '{e.get('channel')}'")
        if e.get("id"):
            ids.add(e["id"])
        f = e.get("file")
        if f and not (root_path() / f).exists():
            errors.append(f"entry {i}: file missing {f}")
        rh = e.get("registered_hash")
        if rh:
            try:
                int(rh, 16)
                if len(rh) != 64:
                    raise ValueError
            except ValueError:
                errors.append(f"entry {i}: registered_hash must be 64 hex chars")
        if e.get("channel") != "ai" and e.get("registered_hash") is None:
            errors.append(f"entry {i}: non-AI captures should give registered_hash (the receipt line)")
    if errors:
        print("\n".join(errors))
        return 1
    print(f"manifest OK: {len(entries)} entries")
    return 0


def run(args) -> int:
    entries = _read_manifest(args.manifest)
    rows, t0 = [], time.time()
    for e in entries:
        rows.append(check_entry_fingerprint(e, root_path()))
    out = {"manifest": str(args.manifest), "n_images": len(rows), "seconds": round(time.time() - t0, 2),
           "thresholds": {"match": T_MATCH, "near": T_NEAR, "duplicate": T_DUP},
           "rows": rows, "note": "fingerprint-only offline check; watermark decode requires the TrustMark model"}
    (root_path().parent / "results").mkdir(exist_ok=True)
    dest = root_path().parent / "results" / args.out
    dest.write_text(json.dumps(out, indent=1))
    print("checked", len(rows), "images ->", dest)
    return 0


def summarize(args) -> int:
    data = json.loads((root_path().parent / "results" / args.out).read_text())
    per_channel = {}
    for r in data["rows"]:
        per_channel.setdefault(r["channel"], []).append(r)
    for ch, rows in per_channel.items():
        ds = [r["registered_distance"] for r in rows if "registered_distance" in r]
        med = sorted(ds)[len(ds) // 2] if ds else None
        print(f"{ch:10} n={len(rows):3d} matched_hashes={sum('registered_distance' in r for r in rows):3d} "
              f"median_dist={med}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    v = sub.add_parser("validate")
    v.add_argument("--manifest", default=str(root_path() / "manifest.json"))
    r = sub.add_parser("run")
    r.add_argument("--manifest", default=str(root_path() / "manifest.json"))
    r.add_argument("--out", default="real_check.json")
    s = sub.add_parser("summarize")
    s.add_argument("--out", default="real_check.json")
    a = ap.parse_args(argv)
    return {"init": init, "validate": validate, "run": run, "summarize": summarize}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())