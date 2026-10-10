# False-rejection investigation (phase 2)

Audit step "investigate the false rejections before changing thresholds". This
document reports what was measured, why thresholds are **not** being changed,
and the concrete, data-backed recommendation for relabelling -- not re-tuning.

These are **real measurements from this repo, reproducible locally**:

```text
python phase2/investigate.py --per-category 100   # fingerprint-only, minutes
python phase2/evaluate.py   --per-category 5      # full watermark run, slower
```

## What fails and what doesn't

1,400 synthetic images (7 categories x 100 images x calibration/held-out,
disjoint seeds, content-hash leak-guarded) under the 21-transform robustness
suite. "Normal sharing" = identity, grayscale, EXIF rotate, blur-light,
resize 50/75, brightness/contrast +/-15%, Messenger, screenshot-like, JPEG q20
to q95.

Ordinary-sharing fingerprint drift **by category** (both splits agree to within
1 bit):

| category    | median | p95 | max | wrongly rejected at T_MATCH=16 |
|-------------|-------:|----:|----:|------------------------------:|
| shapes      |      0 |   2 |   4 |                              0 /600 |
| portraitish |      2 |   4 |  14 |                              0 /600 |
| noise       |     12 |  24 |  34 |                           142 /600 |
| gradient    |   29-30 |  62 | 110 |                          537 /600 |
| symmetry    |     46 |  60 |  70 |                          600 /600 |
| lowcontrast |  64-66 | 106 | 132 |                          500 /600 |
| texture     |  64-66 | 124 | 150 |                          578 /600 |

Structured content (shapes, photo-like portraitish) is stable under ordinary
sharing. Flat / low-texture content (gradients, symmetric gradients,
low-contrast, repeating textures) drifts by dozens of bits under exactly the
transforms people use when sharing images -- JPEG re-encode, resize, message
apps.

## These rejections are not a threshold boundary problem

The full threshold-sensitivity curve over **979,300 unrelated image pairs**:

| threshold | wrongly rejected / 14,700 | false-positive pairs |
|----------:|--------------------------:|---------------------:|
|        10 | 5393                    | 23 |
|        16 | 4747                    | 57 |
|        24 | 4114                    | 182 |
|        30 | 3633                    | 340 |

- The **very first** unrelated collision appears at **threshold 9**; the
  closest unrelated pair is **2 bits apart**.
- Headroom above the current thresholds is therefore **at most ~8 bits**, and
  raising T_MATCH/T_NEAR would add false positives faster than it removes
  false rejections (the rejections sit at distance 29-150, not near the
  boundary).
- A naive "drop the unstable bits" remap is also dead: only **72 of 256**
  positions flip <10% of the time under ordinary sharing (mean 12.2%, p95
  17.6%), not enough to rebuild a 256-bit hash with realistic separation.

**Conclusion: thresholds are not changed.** The failure mode is that the
median-DCT pHash loses discriminability on low-texture images, which causes
*both* directions of error on the same content: big drift under ordinary
sharing (false "altered") and near-collisions between *different* images with
similar flat backgrounds (false "similar"/"duplicate", 57 of 979,300 pairs,
nearest distances 2-4, all within-category).

## The watermark is the reliable signal

Every wrongly-*altered* case was re-examined with the watermark present
(`phase2/evaluate.py`, full run, 35 images/split):

```text
calibration: 94 / 210 wrongly altered     -- 94 had ID decoded exactly (100%)
heldout:     87 / 210 wrongly altered     -- 87 had ID decoded exactly (100%)
```

**100% of the false rejections are cases where the 60-bit ID decoded to the
registered value and only the fingerprint drifted.** The ID is the strong
positive signal; on low-texture content the fingerprint is a weak negative.

## What should change (recommendation, not yet implemented)

1. Decision rule, not threshold: when the watermark ID **decodes exactly to
   the registered ID**, do not let a 16-40 bit fingerprint drift alone
   downgrade the verdict. Reserve "altered" for the edit/anti-tamper band
   (heavy crop / 10-25% paste, distance 50-150 in this corpus). This removes
   essentially all measured false rejections while keeping tamper detection.
   Needs a product call and its own verification test with IDs present, since
   the ID rarely survives real edits (edits wrongly verified today: 1/175).
2. Algorithmic, longer-term: adopt a content-adaptive 256-bit hash (edge /
   color aware) as a **new algorithm id** for low-texture content, evaluated
   against this same corpus before switch-over. The current hash is fine for
   photographic content and is not being replaced blindly.

## Documentation corrections

The earlier phase-2 report ("closest unrelated pair = 100 bits, 0 false
near/dup pairs") was a **small-sample artifact** (2-5 images per category). At
scale the true picture, quantified above, replaces it:

- unrelated minimum distance across 1,400 images: **2** (within-category,
  flat/low-entropy content);
- 57 of 979,300 pairs within the near band, all repeated low-texture content;
- the same low-texture content that collides is what drifts most under sharing.

`phase2/results/investigate.json` and `phase2/results/eval_Q5.json` are the
raw evidence files.