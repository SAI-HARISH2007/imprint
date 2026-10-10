# Real-world channel testing: protocol and harness

Phase 1 and phase 2 measure *simulated* sharing. The three things they cannot
simulate are real message-app transfers, real phone screenshots, and a large
held-out set of AI-generated images. This document defines exactly how to
produce that evidence, and the committed harness (`phase2/channels.py`) that
validates and checks whatever is captured. The captures themselves require
people with phones, apps and models; this repo commits the protocol so that a
contributor anywhere can produce the data in a standard form.

## What we need and why

| Capture | What it answers | Why it is not simulated |
|---|---|---|
| WhatsApp / Telegram real transfers | does the mark and fingerprint survive the real encode pipeline of each app at real sizes? | our `messenger` transform is a guess (1600 px cap, q70); real clients re-encode differently (WebP on WhatsApp, different on Telegram) |
| Phone screenshots | does the mark survive what a display + screenshot pipeline does (dithering, DPCM, Hz issues)? | our `screenshot_like` is a downscale guess |
| Large held-out AI set | can an unrelated AI image *collide* with a registered one, or evade the duplicate guard? | our synthetic corpus is generated, not produced by real diffusion/image models |

The protocol below keeps the fingerprint recipe and the thresholds identical to
the shipped service; `channels.py run` uses the published `fingerprint.py`, so
a result file is comparable to `phase2/results/*.json`.

## Capture protocol

Any contributor with two phones and WhatsApp/Telegram can fill the two message
channels; a phone screenshot needs one phone; the AI set needs access to a
handful of image generators.

1. Run the harness skeleton (creates `phase2/real/<channel>/` and a template
   manifest):
   ```bash
   cd phase2 && python channels.py init
   ```
2. For **whatsapp / telegram**: the creator registers an image on the live
   site, downloads the marked copy, sends it to a second device over the app,
   and the receiver saves the received file with the app's own "save image"
   (not a screenshot). Record in the manifest the receipt line from the
   registration (`registered_id`, `registered_hash`). At least 20 images per
   app; mix JPEG and PNG sources, portraits and scenes.
3. For **screenshot**: the creator has the marked image open on the phone at a
   natural zoom and screenshots it. Record the device and whether it was the
   receiver's phone display (this is the realistic attack surface: someone
   photographs/screenshots a phone showing your image).
4. For **ai**: run the *same unmarked original* through the fingerprint, then
   generate ~30–100 unrelated images per model (Stable Diffusion, Flux, DALL·E,
   Midjourney — whatever is available). These are negatives: nothing here may
   be within 16/24 bits of a registered fingerprint, and none may be a
   near-duplicate of each other. If you also want to test *anti-evasion*, feed
   a marked, registered image into an image editor/inpainting model and record
   what comes back (verbatim received file, plus notes).
5. Fill `phase2/real/manifest.json`, one entry per file, with the exact schema:
   ```json
   {"id": "wa_001", "channel": "whatsapp", "file": "whatsapp/wa_001.jpg",
    "captured_at": "2026-01-15T09:00:00Z",
    "registered_id": "0x…", "registered_hash": "<64 hex>",
    "source_device": "pixel_6", "source_app": "whatsapp_2.24",
    "notes": "JPEG source, sent at original size"}
   ```
   `channel` must be one of `whatsapp`, `telegram`, `screenshot`, `ai`. For
   `ai` entries `registered_hash` is optional and `notes` should name the model
   and the prompt style.
6. Validate and check:
   ```bash
   python channels.py validate --manifest phase2/real/manifest.json
   python channels.py run      --manifest phase2/real/manifest.json --out real_check.json
   python channels.py summarize --out real_check.json
   ```
   Validation is strict (missing files, bad channel, malformed hash all fail);
   `run` writes `phase2/results/real_check.json`, an **offline** fingerprint-only
   check that reports, for every entry, the SHA-256, the fingerprint, and — when
   a registration was given — the bit distance and `verified/likely/different`.
   Watermark decode is intentionally not bundled here (the TrustMark model is a
   service dependency); the site's `/verify` page does the full decode.

## Why the images are not committed

`phase2/real/` is git-ignored. Captures are private (photos of people and
phones) and large; the *artefact* is the manifest plus the result file. A
contributor shares the result file (and only images they are allowed to share).

## What "done" looks like

- ≥20 entries per message channel with verified receipts; every captured copy
  checks `verified` or, if it does not, the manifest notes it and the result
  file shows the actual distance (we report failures, we do not tune them away).
- ≥10 phone screenshots, with any failure visible per device/zoom.
- ≥30 AI negatives per model with 0 within 16/24 bits (`summarize` prints the
  per-channel medians; the gate is the minimum and the number of near pairs).
- The result files and a short write-up appended to `docs/evaluation.md` and
  `README.md` (the "Not yet measured" line is then struck).

This suite is open: without a contributor with the devices/apps/models, the
captures cannot be produced from inside this repo — the harness is built so
that producing them is a fill-in-the-entries task, not a rewrite.