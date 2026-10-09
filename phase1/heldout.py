"""Held-out evaluation with thresholds fixed in advance.

The thresholds in service/verdict.py (match 16, near 24, duplicate 10) were chosen after looking at
the 24 calibration photos in images/. This script never touches those photos. It pulls fresh images
(new seeds, mixed sizes and orientations) plus any AI-generated images dropped into images_ai/, runs
the same damage, and reports what the fixed thresholds do on data they have never seen.

Reported per transform: mark decode rate, and the verdict the product would give.
Reported overall: sharing copies wrongly called "altered", edits wrongly called "verified", and the
false-match rate between unrelated images.

Run:  python heldout.py
"""
import io
import json
import secrets
import statistics
import sys
import urllib.request
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "service"))
import core  # noqa: E402
import verdict  # noqa: E402
from robustness import TRANSFORMS, NORMAL  # noqa: E402

HELD = HERE / "images_heldout"
AI = HERE / "images_ai"
HELD.mkdir(exist_ok=True)
OUT = HERE / "results" / "heldout.json"

SIZES = [(1024, 768), (1600, 1200), (900, 1200), (1280, 720), (800, 800)]


def fetch_heldout(n: int) -> list[Path]:
    paths = []
    for i in range(n):
        w, h = SIZES[i % len(SIZES)]
        p = HELD / f"held_{i:02d}_{w}x{h}.png"
        if not p.exists():
            try:
                data = urllib.request.urlopen(f"https://picsum.photos/seed/imprintH{i}/{w}/{h}", timeout=60).read()
                Image.open(io.BytesIO(data)).convert("RGB").save(p)
            except Exception as e:
                print("download failed:", i, e, file=sys.stderr)
                continue
        paths.append(p)
    return paths


def ai_images() -> list[Path]:
    if not AI.exists():
        return []
    return sorted(p for p in AI.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))


EDIT_KEYS = {"crop_5", "crop_15", "crop_30", "edit_paste_10pct", "edit_paste_25pct"}


def main():
    tm = core._tm()
    nbits = core.payload_bits()
    photos = fetch_heldout(40)
    ais = ai_images()
    sets = {"photos": photos, "ai": ais}
    print(f"held-out photos: {len(photos)}, ai images: {len(ais)}")

    report = {"thresholds": {"match": verdict.T_MATCH, "near": verdict.T_NEAR, "duplicate": verdict.T_DUP}, "sets": {}}
    for set_name, paths in sets.items():
        if not paths:
            continue
        imgs = [Image.open(p).convert("RGB") for p in paths]
        per = {k: {"decoded": 0, "verdicts": {}, "dists": []} for k in TRANSFORMS}
        fps = []
        wrong_altered = wrong_verified = 0
        for idx, cover in enumerate(imgs):
            bits = "".join(secrets.choice("01") for _ in range(nbits))
            marked = tm.encode(cover, bits, MODE="binary").convert("RGB")
            fp0 = core.fingerprint(marked)
            fps.append(fp0)
            rec = verdict.Record(core.bits_to_id(bits), fp0, "0xsigner", 1)
            donor = imgs[(idx + 1) % len(imgs)]
            for name, fn in TRANSFORMS.items():
                out = fn(marked, donor)
                try:
                    secret, present, _ = tm.decode(out, MODE="binary")
                except Exception:
                    secret, present = "", False
                ok = bool(present) and secret == bits
                fp = core.fingerprint(out)
                d = core.distance(fp, fp0)
                v = verdict.decide(ok, core.bits_to_id(secret) if ok else None, fp, rec if ok else None, [rec])["verdict"]
                per[name]["decoded"] += int(ok)
                per[name]["verdicts"][v] = per[name]["verdicts"].get(v, 0) + 1
                per[name]["dists"].append(d)
                if name in NORMAL and v == "altered":
                    wrong_altered += 1
                if name in EDIT_KEYS and v == "verified":
                    wrong_verified += 1
            print(f"  {set_name} {idx + 1}/{len(imgs)}", flush=True)

        n = len(imgs)
        # false matches between unrelated images, using the fixed thresholds
        pairs = [(i, j) for i in range(n) for j in range(n) if i < j]
        unrelated = [core.distance(fps[i], fps[j]) for i, j in pairs]
        false_near = sum(1 for d in unrelated if d <= verdict.T_NEAR)
        false_dup = sum(1 for d in unrelated if d <= verdict.T_DUP)

        report["sets"][set_name] = {
            "n_images": n,
            "per_transform": {
                k: {
                    "decode_rate": v["decoded"] / n,
                    "verdicts": v["verdicts"],
                    "median_dist": statistics.median(v["dists"]),
                    "max_dist": max(v["dists"]),
                }
                for k, v in per.items()
            },
            "normal_sharing_mean_decode": statistics.mean(per[k]["decoded"] / n for k in NORMAL),
            "sharing_wrongly_altered": wrong_altered,
            "sharing_checks": n * len(NORMAL),
            "edits_wrongly_verified": wrong_verified,
            "edit_checks": n * len(EDIT_KEYS & set(TRANSFORMS)),
            "unrelated_pairs": len(pairs),
            "unrelated_min_dist": min(unrelated),
            "false_likely_match_pairs": false_near,
            "false_duplicate_pairs": false_dup,
        }
        s = report["sets"][set_name]
        print(f"{set_name}: normal-sharing decode {s['normal_sharing_mean_decode']:.0%}, "
              f"sharing wrongly altered {wrong_altered}/{s['sharing_checks']}, edits wrongly verified {wrong_verified}/{s['edit_checks']}, "
              f"unrelated min dist {s['unrelated_min_dist']}, false likely-match pairs {false_near}/{len(pairs)}")

    OUT.write_text(json.dumps(report, indent=1))
    print("written", OUT)


if __name__ == "__main__":
    main()
