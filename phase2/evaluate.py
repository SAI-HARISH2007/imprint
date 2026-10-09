"""Phase 2 evaluation: a leak-checked, reproducible robustness suite.

Marks a generated corpus (phase2/corpus.py, no downloads), damages each image
with the same transforms as phase 1, and reports:

- image-level: which individual images are weak under ordinary sharing;
- transform-level: per-transform decode rate and fingerprint drift;
- negatives: fingerprint distance between unrelated images, split by category,
  so adversarial categories (symmetry, lowcontrast) can be inspected directly;
- leakage: the calibration/held-out guard is enforced before anything is scored.

Thresholds are the product's (service/verdict.py), fixed, never tuned here.

Run:
    python evaluate.py --per-category 2                 # watermark + fingerprint (slow)
    python evaluate.py --per-category 50 --fingerprint-only   # fingerprint only (fast, scales)
    python evaluate.py --json-out results/eval.json
"""
import argparse
import json
import secrets
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "service"))
sys.path.insert(0, str(HERE.parent / "phase1"))

import core  # noqa: E402
import verdict  # noqa: E402
from corpus import CATEGORIES, check_no_leakage, generate  # noqa: E402
from robustness import NORMAL, TRANSFORMS  # noqa: E402

EDIT_KEYS = {"crop_5", "crop_15", "crop_30", "edit_paste_10pct", "edit_paste_25pct"}
ADVERSARIAL = {"symmetry", "lowcontrast"}
OUT_DIR = HERE / "results"


def run_split(samples, tm, nbits, watermark: bool) -> dict:
    imgs = [s.img for s in samples]
    fps, rows = [], []
    n = len(samples)
    for idx, s in enumerate(samples):
        if watermark:
            bits = "".join(secrets.choice("01") for _ in range(nbits))
            marked = tm.encode(s.img, bits, MODE="binary").convert("RGB")
        else:
            bits, marked = None, s.img
        fp0 = core.fingerprint(marked)
        fps.append(fp0)
        rec = verdict.Record(core.bits_to_id(bits) if bits else "0x0", fp0, "0xsigner", 1)
        donor = imgs[(idx + 1) % n]
        for tname, fn in TRANSFORMS.items():
            out = fn(marked, donor)
            if watermark:
                try:
                    secret, present, _ = tm.decode(out, MODE="binary")
                except Exception:
                    secret, present = "", False
                ok = bool(present) and secret == bits
            else:
                secret, ok = "", False
            fp = core.fingerprint(out)
            dist = core.distance(fp, fp0)
            v = verdict.decide(
                ok, core.bits_to_id(secret) if ok else None, fp, rec if ok else None, [rec]
            )["verdict"]
            rows.append({"image": s.name, "category": s.category, "transform": tname,
                         "decoded": ok, "dist": dist, "verdict": v})
        print(f"  {s.name} {idx + 1}/{n}", flush=True)

    per_t = {}
    for r in rows:
        per_t.setdefault(r["transform"], []).append(r)
    transforms = {
        t: {
            "decode_rate": sum(r["decoded"] for r in rs) / n,
            "verdicts": _counts(r["verdict"] for r in rs),
            "median_dist": statistics.median(r["dist"] for r in rs),
            "max_dist": max(r["dist"] for r in rs),
        }
        for t, rs in per_t.items()
    }

    # image-level
    per_image = {}
    for s in samples:
        rs = [r for r in rows if r["image"] == s.name]
        normal = [r for r in rs if r["transform"] in NORMAL]
        per_image[s.name] = {
            "category": s.category,
            "normal_decode_rate": sum(r["decoded"] for r in normal) / len(normal),
            "max_normal_dist": max(r["dist"] for r in normal),
            "wrongly_altered": sum(1 for r in normal if r["verdict"] == "altered"),
        }
    weak = sorted(per_image.items(), key=lambda kv: (kv[1]["normal_decode_rate"], -kv[1]["max_normal_dist"]))

    # negatives: unrelated pairs within the split, and per-category minimum
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    dists = [core.distance(fps[i], fps[j]) for i, j in pairs]
    per_cat = {}
    for cis in CATEGORIES:
        idxs = [i for i, s in enumerate(samples) if s.category == cis]
        ds = [core.distance(fps[i], fps[j]) for a, i in enumerate(idxs) for j in idxs[a + 1:]]
        if ds:
            per_cat[cis] = {"min_unrelated_dist": min(ds), "median_unrelated_dist": statistics.median(ds)}

    wrong_altered = sum(p["wrongly_altered"] for p in per_image.values())
    wrong_verified = sum(1 for r in rows if r["transform"] in EDIT_KEYS and r["verdict"] == "verified")
    return {
        "n_images": n,
        "per_transform": transforms,
        "per_image": per_image,
        "weakest_images": [{"image": k, **v} for k, v in weak[:5]],
        "normal_sharing_mean_decode": statistics.mean(transforms[t]["decode_rate"] for t in NORMAL),
        "sharing_wrongly_altered": wrong_altered,
        "sharing_checks": n * len(NORMAL),
        "edits_wrongly_verified": wrong_verified,
        "edit_checks": n * len(EDIT_KEYS),
        "unrelated_pairs": len(pairs),
        "unrelated_min_dist": min(dists) if dists else None,
        "false_likely_match_pairs": sum(d <= verdict.T_NEAR for d in dists),
        "false_duplicate_pairs": sum(d <= verdict.T_DUP for d in dists),
        "per_category_unrelated": per_cat,
    }


def _counts(it):
    out = {}
    for x in it:
        out[x] = out.get(x, 0) + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-category", type=int, default=2)
    ap.add_argument("--model", default="Q")
    ap.add_argument("--fingerprint-only", action="store_true",
                    help="skip the watermark model; evaluates fingerprint + leakage only (fast)")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    calib = generate("calibration", args.per_category)
    held = generate("heldout", args.per_category)
    check_no_leakage(calib, held)  # raises LeakageError if any overlap
    print(f"corpus: calibration={len(calib)} heldout={len(held)}  leak guard OK")

    tm = None if args.fingerprint_only else core._tm()
    nbits = 0 if args.fingerprint_only else core.payload_bits()
    if not args.fingerprint_only:
        print(f"TrustMark model={args.model}, payload bits={nbits}")

    report = {
        "mode": "fingerprint-only" if args.fingerprint_only else "watermark+fingerprint",
        "model": args.model,
        "per_category": args.per_category,
        "thresholds": {"match": verdict.T_MATCH, "near": verdict.T_NEAR, "duplicate": verdict.T_DUP},
        "leak_guard": "passed (disjoint seed banks + content-hash check)",
        "sets": {},
    }
    for name, samples in (("calibration", calib), ("heldout", held)):
        print(f"running {name}...")
        report["sets"][name] = run_split(samples, tm, nbits, watermark=not args.fingerprint_only)

    # cross-split negatives: fingerprints from calibration vs held-out
    cal_fps = [core.fingerprint(s.img) for s in calib]
    held_fps = [core.fingerprint(s.img) for s in held]
    cross = [core.distance(a, b) for a in cal_fps for b in held_fps]
    report["cross_split_unrelated_min_dist"] = min(cross) if cross else None

    for name in ("calibration", "heldout"):
        s = report["sets"][name]
        print(f"\n{name}: n={s['n_images']}  normal-sharing decode {s['normal_sharing_mean_decode']:.0%}  "
              f"wrongly altered {s['sharing_wrongly_altered']}/{s['sharing_checks']}  "
              f"edits wrongly verified {s['edits_wrongly_verified']}/{s['edit_checks']}  "
              f"unrelated min dist {s['unrelated_min_dist']}")
        print("  weakest images:", ", ".join(f"{w['image']}({w['normal_decode_rate']:.0%})" for w in s["weakest_images"]))

    if args.json_out:
        OUT_DIR.mkdir(exist_ok=True)
        out = OUT_DIR / args.json_out
        out.write_text(json.dumps(report, indent=1))
        print("written", out)


if __name__ == "__main__":
    main()
