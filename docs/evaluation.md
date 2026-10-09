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
python evaluate.py --per-category 5 --json-out eval_Q5.json   # reference watermark run
python evaluate.py --per-category 500 --fingerprint-only      # scales to thousands, fast
python investigate.py --per-category 100 --json-out investigate.json  # false-rejection sweep
python -m pytest test_corpus.py test_investigate.py           # fast corpus/leak/recipe tests
```

Runtime is dominated by the TrustMark encode/decode, not the image generation:
the reference watermark run below is 35 images per split (1400 fingerprint-only
is minutes). Generating thousands is cheap; *marking* hundreds is the slow part,
which is why the watermark run is parameterised rather than fixed.

## Results (committed runs)

- `results/eval_Q.json` — 14 images per split, the original small demonstration.
- `results/eval_Q5.json` — 35 images per split, the current reference run
  (numbers below); it adds the "wrongly altered but ID decoded" split per image.
- `results/investigate.json` — the 1,400-image, fingerprint-only false-rejection
  sweep (see also `docs/false-rejections.md`).

Ordinary sharing, watermark and fingerprint (`eval_Q5.json`, 35/split):

| transform | calib decode | calib med/max drift | held-out decode | held-out med/max drift |
|---|---|---|---|---|
| identity | 100% | 0 / 0 | 100% | 0 / 0 |
| png→jpeg q95 | 100% | 12 / 38 | 100% | 12 / 32 |
| jpeg q90 | 100% | 14 / 34 | 100% | 14 / 38 |
| jpeg q70 | 94% | 22 / 58 | 97% | 22 / 72 |
| jpeg q50 | 80% | 24 / 80 | 77% | 24 / 96 |
| jpeg q30 | 66% | 30 / 96 | 54% | 32 / 94 |
| jpeg q20 | 34% | 40 / 92 | 26% | 40 / 110 |
| resize 75 / 50 / 25 | 100% each | 10–18 / 34–42 | 100% each | 12–16 / 44–56 |
| messenger | 94% | 22 / 58 | 97% | 22 / 72 |
| screenshot-like | 89% | 28 / 56 | 94% | 20 / 52 |
| crop 5% / 15% / 30% | 100% / 100% / 0% | 42 / 102 / 116 | 100% / 100% / 0% | 48 / 104 / 120 |
| brightness ±15% | 100% | 14–20 / 54–62 | 100% | 12–20 / 46–64 |
| contrast +15% | 97% | 18 / 58 | 100% | 16 / 52 |
| edit paste 10% / 25% | 71% / 6% | 84 / 88 | 63% / 6% | 64 / 84 |

Negative controls and the leakage guard:

| | calibration | held-out |
|---|---|---|
| unrelated pairs, minimum distance | 80 bits | 64 bits |
| `/verify` false *altered* but **ID decoded** | 94 / 94 | 87 / 87 |
| edits wrongly called *verified* | 1 / 175 | 0 / 175 |
| leakage guard | passed | passed |

The 1,400-image sweep overturns the tidy negatives of the 14-image run: the
global unrelated minimum drops to **2 bits**, with **57 of 979,300 pairs**
within 16 bits — all *different images with the same flat background* (gradient
27, portraitish-proxy 29, texture 1; nearest distances 2–4). See
`docs/false-rejections.md`.

## What these runs show

1. **At scale, low-entropy content collapses the hash.** The median-DCT
   fingerprint cannot separate different images that share a flat/low-texture
   background — the closest unrelated pair at 1,400 images is 2 bits.
   The 14-image run (min 100 bits, 0 false pairs) was a small-sample artifact.
2. **Every false *altered* call had the watermark ID decoded.** The ID is the
   reliable signal; on low-texture content the fingerprint is a weak negative.
   Raising thresholds is not the fix — headroom is ~8 bits before unrelated
   collisions — so the recommendation is a decision-rule change (decoded ID is
   authoritative; reserve *altered* for edit-scale drift), not a re-tune.
3. **Edits are never mistaken for the original** (0–1/175 wrongly *verified*),
   which is the property that matters for the "altered" verdict.
4. **A real weakness, made visible:** synthetic texture drifts the fingerprint
   *much* more than real photos. In phase 1, ordinary sharing stayed within ~12
   bits; here even `png→jpeg q95` has a median drift of 10 and a max of 36, so
   94–87 of 210 ordinary-sharing checks are labelled *altered* on flat/low-texture
   content while the watermark still decodes exactly.
5. **The watermark degrades as expected**: robust to resize and q50+, weak at
   q20 (14–36% decode) and gone past 25% crops or 25% paste — matching phase 1.

## Limits (stated plainly)

- These are **synthetic** images. They stress the fingerprint with texture the
  real photos do not, which is why they find the drift; but they do not
  reproduce sensor noise, lens blur or real compression pipelines.
- The reference run is 35 images per split for the watermark and 100 per
  category for the fingerprint-only sweep; both are reproducible commands, and
  the watermark run scales with compute.
- Still not covered by any suite: real WhatsApp/Telegram transfers and real
  phone screenshots, and a large AI-generated set. Those remain open and are
  listed as such.
