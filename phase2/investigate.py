"""Investigate the fingerprint's false rejections BEFORE changing any threshold.

The committed phase 2 run showed that synthetic textures drift the 256-bit
phash far more than real photos: 36-42 of 84 ordinary-sharing checks exceed
T_MATCH=16 and are branded "altered" even though the watermark decodes. This
script characterises that drift on a large corpus and decides, with data,
whether and how to act:

1. per-transform drift (median / p95 / max) and how many NORMAL-sharing rows
   would be wrongly rejected at T_MATCH=16, split by category;
2. the threshold sensitivity curve: how much headroom exists before the FIRST
   unrelated image pair collides (the true-negative bound) — the empirical
   maximum safe threshold;
3. per-bit-position flip rates under ordinary sharing, so a "stable-bit subset"
   hash can be judged with numbers instead of guessed.

It computes fingerprints with the published spec (parity-checked against
fingerprint.py) and never changes production thresholds or the algorithm.

Run (fingerprint-only, no model; ~seconds per 100 images):
    python investigate.py --per-category 150 --json-out results/investigate.json
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.fftpack import dct

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "service"))
sys.path.insert(0, str(HERE.parent / "phase1"))

import fingerprint as fp  # noqa: E402
from corpus import generate, check_no_leakage  # noqa: E402
from robustness import NORMAL, TRANSFORMS  # noqa: E402

SIZE64 = (64, 64)


def coeffs(img: Image.Image) -> np.ndarray:
    """16x16 low-frequency DCT block exactly as the published spec."""
    a = np.asarray(img.convert("L").resize(SIZE64, Image.LANCZOS), dtype=np.float64)
    d = dct(dct(a, axis=0, norm=None), axis=1, norm=None)
    return d[:16, :16]


def bits(c: np.ndarray) -> np.ndarray:
    return (c > np.median(c)).astype(np.uint8).reshape(256)


def hashstr(c: np.ndarray) -> str:
    vals = bits(c)
    return hex(int("".join(map(str, vals)), 2))[2:].zfill(64)


def p95(ds):
    s = sorted(ds)
    return s[min(len(s) - 1, int(len(s) * 0.95) - 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-category", type=int, default=100)
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    cal0 = generate("calibration", 1)
    for s in cal0:
        assert hashstr(coeffs(s.img)) == fp.compute(s.img), "local recipe drifts from fingerprint.py"
    print("parity with fingerprint.py: OK")

    report = {"per_category": args.per_category, "upstream": {"T_MATCH": 16, "T_NEAR": 24}, "sets": {}}
    all_bits = []
    flip_pos = np.zeros(256, dtype=np.int64)
    flip_counts = np.zeros(256, dtype=np.int64)
    normal_rows = []

    for split in ("calibration", "heldout"):
        samples = generate(split, args.per_category)
        imgs = [s.img for s in samples]
        base_b = [bits(coeffs(im)) for im in imgs]
        rows = []
        all_bits.extend(base_b)
        for idx, s in enumerate(samples):
            donor = imgs[(idx + 1) % len(imgs)]
            for tname, fn in TRANSFORMS.items():
                c = coeffs(fn(s.img, donor))
                b = bits(c)
                dist = int((base_b[idx] ^ b).sum())
                rows.append({"image": s.name, "category": s.category, "transform": tname, "dist": dist})
                if tname in NORMAL:
                    flip_pos += (base_b[idx] ^ b).astype(np.int64)
                    flip_counts += 1
                    normal_rows.append(rows[-1])
            print(f"  {split} {s.name} {idx + 1}/{len(samples)}", flush=True)
        report["sets"][split] = summarize(samples, rows)

    check_no_leakage(generate("calibration", args.per_category), generate("heldout", args.per_category))
    report["leak_guard"] = "passed"

    n = len(all_bits)
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    dists = [int((all_bits[i] ^ all_bits[j]).sum()) for i, j in pairs]
    report["unrelated_pairs"] = len(pairs)
    report["unrelated_min_dist"] = min(dists)

    # threshold sensitivity: wrong rejections at each threshold vs first collision
    seq = []
    first_fp = None
    for t in range(9, 46):
        wrong = sum(1 for r in normal_rows if r["dist"] > t)
        fpos = sum(1 for d in dists if d <= t)
        if first_fp is None and fpos > 0:
            first_fp = t
        seq.append({"threshold": t, "wrong_rejections": wrong, "false_positives": fpos})
    report["threshold_curve"] = seq
    report["first_unrelated_collision_at"] = first_fp

    rate = flip_pos / np.maximum(flip_counts, 1)
    report["bit_position_flip_rate"] = {
        "observations": int(flip_counts.max()),
        "mean": round(float(rate.mean()), 4),
        "p95": round(float(np.percentile(rate, 95)), 4),
        "stable_<5%": int((rate < 0.05).sum()),
        "stable_<10%": int((rate < 0.10).sum()),
        "least_stable_bits": [int(i) for i in np.argsort(-rate)[:8]],
    }

    for name in ("calibration", "heldout"):
        print_report(name, report["sets"][name])
    print(f"\nunrelated pairs: {report['unrelated_pairs']}, min distance: {report['unrelated_min_dist']} "
          f"; first unrelated collision at threshold {report['first_unrelated_collision_at']}")

    if args.json_out:
        (HERE / "results").mkdir(exist_ok=True)
        out = HERE / "results" / args.json_out
        out.write_text(json.dumps(report, indent=1))
        print("written", out)


def summarize(samples, rows):
    per_t, per_cat = {}, {}
    for r in rows:
        per_t.setdefault(r["transform"], []).append(r)
        if r["transform"] in NORMAL:
            per_cat.setdefault(r["category"], []).append(r)
    transforms = {}
    for t, rs in per_t.items():
        ds = [r["dist"] for r in rs]
        transforms[t] = {"median": statistics.median(ds), "p95": p95(ds), "max": max(ds),
                          "wrong_rejected_gt16": sum(d > 16 for d in ds)}
    cats = {}
    for cat, rs in per_cat.items():
        ds = [r["dist"] for r in rs]
        cats[cat] = {"n": len(rs), "median": statistics.median(ds), "p95": p95(ds), "max": max(ds),
                      "wrong_rejected_gt16": sum(d > 16 for d in ds)}
    return {"n_images": len(samples), "per_transform": transforms, "per_category": cats}


def print_report(name, s):
    print(f"\n== {name} (n={s['n_images']}) ==")
    print(f"  {'transform':<18} {'median':>6} {'p95':>5} {'max':>5}  wrong>16")
    for t, v in s["per_transform"].items():
        print(f"  {t:<18} {v['median']:>6} {v['p95']:>5} {v['max']:>5}  {v['wrong_rejected_gt16']:>8}")
    print("  per category (NORMAL transforms):")
    for cat, v in s["per_category"].items():
        print(f"    {cat:<12} median {v['median']:>3}  p95 {v['p95']:>3}  max {v['max']:>3}  wrong>16 {v['wrong_rejected_gt16']}")


if __name__ == "__main__":
    main()