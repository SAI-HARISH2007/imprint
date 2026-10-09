# The phase 2 evaluation: a larger, leak-checked synthetic sweep

Phase 1's robustness evidence rests on 24 calibration photos and 40 held-out
photos from a stock source, with one disclosed overlap — too few and too
homogeneous to say *where* the method fails. Phase 2 adds a reproducible,
offline, leak-checked suite in `phase2/` that can generate as many images as you
ask for. It complements phase 1; it does not replace real photographs.

## What it does

- **`phase2/corpus.py`** generates a synthetic corpus across seven categories
  with no network access: `gradient`, `lowcontrast`, `symmetry`, `noise`,
  `shapes`, `texture`, `portraitish`. The last three are chosen as hard cases for
  a DCT perceptual hash (few low-frequency coefficients, near-mirror symmetry).
- **Leakage guard.** Calibration and held-out images are drawn from *disjoint
  seed banks* (`0` vs `1_000_000`), so a held-out image can never be a transform
  of a calibration one, and a **content-hash check runs before anything is
  scored** and raises `LeakageError` on any overlap. This is the guarantee phase
  1 could not make. `test_corpus.py` proves the guard catches a deliberate leak.
- **`phase2/evaluate.py`** marks each image, applies the same transforms as phase
  1, and reports **image-level** results (which images are weak) and
  **transform-level** results (decode rate, fingerprint drift, verdicts), plus
  **negatives split by category** so adversarial categories are visible.

Thresholds are the product's (`service/verdict.py`: 16 / 24 / 10), fixed and
never tuned here.

## Running it

```bash
cd phase2
python evaluate.py --per-category 2                 # watermark + fingerprint
python evaluate.py --per-category 500 --fingerprint-only   # scales to thousands, fast
python evaluate.py --per-category 2 --json-out eval_Q.json
python -m pytest test_corpus.py                     # fast corpus/leak tests
```

Runtime is dominated by the TrustMark encode/decode, not the image generation:
the committed run below is 28 images (14 per split). Generating thousands is
cheap; *marking* thousands is the slow part, which is why the watermark run is
parameterised rather than fixed.

## Results (committed run, `results/eval_Q.json`, 14 images per split)

Ordinary sharing, watermark and fingerprint:

| transform | calib decode | calib med/max drift | held-out decode | held-out med/max drift |
|---|---|---|---|---|
| identity | 100% | 0 / 0 | 100% | 0 / 0 |
| png→jpeg q95 | 100% | 10 / 36 | 100% | 10 / 22 |
| jpeg q90 | 100% | 12 / 42 | 100% | 14 / 28 |
| jpeg q70 | 93% | 18 / 58 | 100% | 24 / 62 |
| jpeg q50 | 79% | 28 / 78 | 71% | 25 / 76 |
| resize 75 / 50 / 25 | 100% | 13–16 / 40–48 | 100% | 13–23 / 22–46 |
| messenger | 93% | 18 / 58 | 100% | 24 / 62 |
| screenshot-like | 100% | 23 / 52 | 93% | 26 / 44 |
| crop 5% / 15% / 30% | 100% / 100% / 0% | 44 / 107 / 119 | 100% / 100% / 0% | 53 / 110 / 119 |
| brightness ±15% | 100% | 13–21 / 66–68 | 100% | 14–20 / 44–50 |
| edit paste 10% / 25% | 79% / 0% | 90 / 105 | 64% / 7% | 77 / 89 |

Negative controls and the leakage guard:

| | calibration | held-out |
|---|---|---|
| unrelated pairs, minimum distance | 100 bits | 100 bits |
| false *likely-match* pairs (≤24) | 0 | 0 |
| false *duplicate* pairs (≤10) | 0 | 0 |
| per-category unrelated minimum | 100–126 | 100–154 |
| edits wrongly called *verified* | 0 / 70 | 0 / 70 |
| leakage guard | passed | passed |

## What this run shows

1. **The negatives are clean.** Even the adversarial categories
   (`lowcontrast`, `symmetry`) never put two unrelated images within the
   near-match radius; the closest unrelated pair across all categories is 100
   bits of 256. No false provenance.
2. **Edits are never mistaken for the original** (0/70 wrongly *verified*),
   which is the property that matters for the "altered" verdict.
3. **A real weakness, made visible:** synthetic texture drifts the fingerprint
   *much* more than real photos. In phase 1, ordinary sharing stayed within ~12
   bits; here even `png→jpeg q95` has a median drift of 10 and a max of 36, so
   **36–42 of 84 ordinary-sharing checks are labelled *altered*** — while the
   watermark still decodes exactly (100% for q95/q90). On flat/low-texture
   content the 256-bit median threshold is brittle, and the fix is a
   per-category or content-aware threshold (or a larger hash grid), not a
   weaker one.
4. **The watermark degrades as expected**: robust to resize and q50+, weak at
   q20 (14–36% decode) and gone past 25% crops or 25% paste — matching phase 1.

## Limits (stated plainly)

- These are **synthetic** images. They stress the fingerprint with texture the
  real photos do not, which is why they find the drift; but they do not
  reproduce sensor noise, lens blur or real compression pipelines.
- The committed run is 14 images per split. It is a demonstration of the
  harness, not the "thousands of images" target; scaling the corpus is a command
  away, and scaling the *watermark* run needs compute.
- Still not covered by any suite: real WhatsApp/Telegram transfers and real
  phone screenshots, and a large AI-generated set. Those remain open and are
  listed as such.
