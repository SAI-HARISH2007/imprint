# Imprint

**Register an image with a passkey. A compressed, resized or screenshotted copy can still be checked against a public record on Monad, and an edited copy is told apart from a merely re-encoded one.**

Built for the Monad Metropolis hackathon, Track 4 (Trust, Identity and AI Infrastructure), answering the brief line *"provenance for generated media that survives re-encoding"*.

- Registry contract on Monad testnet: [`0xf4a792ddb0c83Bdf1Ed2E1220B197760d821396c`](https://testnet.monadvision.com/address/0xf4a792ddb0c83Bdf1Ed2E1220B197760d821396c) (chain 10143, source verified by Sourcify).
- Live demo: https://imprint-ten-theta.vercel.app (API: https://sai-harish2007--imprint-api-api.modal.run)
- Demo video: *link added at submission*

This repository contains the implementation, the evaluation harness that quantifies the claims below, the scripts that reproduce every number, and the docs that explain the security model. It is a hackathon prototype, not audited production software.

---

## What Imprint does

1. **Watermarks** an image with a hidden 61-bit payload (the record ID), using TrustMark Q with BCH-5 error correction. The mark survives JPEG re-encoding and downscaling; it detects and resists the common "re-encode to strip the watermark" attack.
2. **Fingerprints** the image with a perceptual hash (`phash-dct-16x16-v1`), so a *resized/recompressed* copy still matches the original record (distance ≤ 16), while a *genuinely edited* copy does not (distance > 24).
3. **Registers** the same ID that is embedded in the image on an append-only contract, authenticated by a **WebAuthn passkey** — no signing key on the server, no account, nothing identifiable stored on chain. Registration is free to the creator; the service pays the gas.
4. **Verifies** later copies entirely on-chain: the image that shows up anywhere on the internet is checked against the registry (`POST /verify` reports the five-verdict result), and `POST /stress` reproduces the robustness matrix live for any registered image.
5. **Sends a receipt** for every registration: a signed JSON file whose every field is cross-examined against the live registry when it is checked.

### Guarantees vs. non-guarantees — read this first

| Guaranteed | Not guaranteed |
|---|---|
| A registered image can be identified after re-encoding, resizing, scaling, cropping to working margins and channel/clip edits. | "Keep my image un-copyable at rest." The registry is an *after-the-fact provenance ledger*; it does not prevent a screenshot being taken. The watermark is protection only while the image content is unchanged — cropping someone's watermark *region* out can strip it, because the mark is spread across the image and a cropped copy omits parts of that spread. |
| An edited copy is told apart from a re-encoded one (≥ 19 bits of distance; thresholds 16/24). | Clear-cut protection against *object-removal* or *background-substitution*. Those move the distance above 24, so the copy is flagged **altered**, not verified — which is the correct and safe failure mode. |
| A stripped-re-encode is caught (encoder is not used to "clean" someone's watermark). | Protection against a determined *human* attacker who does the stripping by hand. |
| The watermark is ~61 bits of randomness, ID presence is checked, the signature is passkey-owned. | Mathematical proof against a *targeted* exhaustive collision search. |
| The record lists `signer` (a public key) and `timestamp`. | "The owner of this image is this person." Registering a photo with a passkey proves the signer *registered it at that time* — it does not prove first authorship, does not prove the passkey holder took the photo, and it is evidence, not a court judgment. |
| The fingerprint identifies an image that was registered. | "This image is real / has no AI edits." The kind of edit is revealed, but protections never make a *re-encoding* a forgery. |
| Tamper-evidence: a `register` returning a wrong hash would be caught, and copies passed to the verifier are fingerprinted and hashed. | Protection against a malicious *read* node feeding the web an altered copy, or a malicious creator registering someone else's photo after editing it first. |

Evidence for every claim in this table is in [`docs/evaluation.md`](docs/evaluation.md) and reproduced by commands in [Run it yourself](#run-it-yourself).

---

## Architecture

```
                ┌────────────────────────────────────┐
                │              web (Next.js)          │
                │  register · verify · my work ·      │
                │  r/[id] · receipts · stress         │
                └───────────────┬────────────────────┘
                                │ HTTP
                                v
        ┌───────────────────────────────────────────┐
        │               service (FastAPI)            │
        │                                            │
        │  /register                                 │
        │    TrustMark → 61-bit ID + marked PNG      │
        │    fingerprint (phash)                     │
        │    claim token (marked bytes held server-  │
        │      side, never released before on-chain) │
        └───────────────┬────────────────┬───────────┘
                        │                │
          /claim, /mark                /verify /check /records
          relay                      receipt/verify · read RPC
                        │                │
                        v                v
   ┌──────────────────────────────────────────────┐
   │  ImprintRegistry (Monad testnet 10143)        │
   │  append-only  id → {signer, fingerprint,      │
   │                    timestamp, block}          │
   │  passkey = P-256 public key  →  signer        │
   │  unique-id collision   →  RejectWithError     │
   │  no owner, no upgrade, no fee, no pause       │
   └──────────────────────────────────────────────┘
```

Data flow for verification: any detector re-hashes the *copy* with the same `phash` recipe, queries the registry for the closest fingerprint, and that record's `signer`/timestamp is what a receipt check or `/verify` reports. Nothing about the block is hidden — the full pipeline is in this repo and reproduces exactly.

---

## How registration works

1. **Mark.** The creator uploads a PNG/JPEG. The service picks a random 61-bit ID and embeds it with TrustMark (BCH-5, watermarked quality 70 — the same compression a social app would apply is what the model is told is "the original"). If the self-test at q70 with strengths escalated offline fails, the request is rejected (model integrity check). **`decode(watermarked image) == id` is the simulation gate.**
2. **Challenge.** The browser builds the WebAuthn challenge from an EIP-712 digest of `(registry, chainId, id, fingerprint)`. The digest is what the Chromium dialog asks the user to "sign" with their passkey. No account, no server-side signature.
3. **Relay.** The P-256 public key `(qx, qy)` and assertion are sent to `POST /register`. The contract verifies the assertion through Monad's P-256 precompile at `0x0100`, derives `signer = uint160(uint256(keccak256(abi.encode(qx, qy))))` and stores it. A signed EIP-712 path (`registerSigned` with an EOA) exists for wallets without a passkey. The relayer (the key that pays the gas) cannot register anything in anyone else's name — the signature must verify against the recorded signer. Each record carries its own fingerprint, the verifier matches on it, and the same ID never registers twice.
4. **Reveal.** The marked PNG is held server-side until the ID is on chain (`/register` returns it, or `/claim` returns it once the record exists). This closes the front-running window where an observer could read the hidden ID from a returned PNG and register it first. Claims are in-memory, single-use, 15-minute TTL.

The smart contract is `registerPasskey(...)` (and `registerSigned(...)` for EIP-712 EOAs) plus view functions. It contains **no owner, no upgrade path, no fee and no pause** — the registry is append-only and can be read by anyone (verified against `contracts/src/ImprintRegistry.sol`; the enumerated trust model is in [`docs/enforcement.md`](docs/enforcement.md)).

---

## The two signals

### Watermark — 61-bit ID, TrustMark Q (BCH-5)

- The ID is 61 independent payload bits (BCH-5 error correction inside TrustMark Q). Only a full 61-bit match is treated as the record; a partial or noisy decode is not.
- Survivability is checked by a **self-test on every mark**: `core.mark` decodes the pristine PNG *and* a JPEG q70 copy of the result, and if either fails it escalates the strength (1.0 → 1.5 → 2.0) and embeds again — a mark that cannot decode at q70 is refused. `evaluate.py` runs the full robustness matrix on the datasets in the next section. The encoder is *not* used to verify — an adversarial `decode` is.
- The mark is only as strong as the least-common content: **flat regions and low texture limit the mark**; on such content a crop can strip a mark despite the escalation.
- Known limitations are enumerated in [`docs/fingerprint.md`](docs/fingerprint.md): if the mark point is chopped out the ID is gone with it. This is why the *perceptual* fingerprint is the actual registry key and the watermark is an integrity layer.

### Fingerprint — `phash-dct-16x16-v1`

`service/fingerprint.py` implements the stable spec in [`docs/fingerprint.md`](docs/fingerprint.md) and is what makes "tell apart a re-encode from an edit" possible:

- JPEG-decode → trapezoid-crop to working margins → resize to 2048 long side → 16×16 DCT → take the 10×10 low-frequency block (round coefficients) → median-threshold into 100 bits.
- Distances are **Hamming**: the number of bits that differ. The pipeline does not know "this edit is 3 bits", it knows the observed distance on real copies and thresholds.
- The spec is versioned and the algorithm is recorded per record (so a v2 — e.g. a locality-sensitive hash — can be introduced without breaking old records).

Thresholds in `service/verdict.py`:

| Distance | Verdict |
|---|---|
| ≤ 16 | **verified** |
| 17–24 | **likely match** — could be unusually heavy re-encoding with low-texture content |
| ≥ 25 | **altered** — statistically consistent with an edit |
| earlier record ≤ 10, different signer | **disputed** — a near-identical image was registered first |

The `disputed` verdict is computed by the service at check time (requiring the incoming ID to decode so a *record* exists, then finding an earlier lookalike ≤ 10 bits from a different signer). The contract-side `disputeDuplicate`/`isDisputed`/`disputeOf` implementation is written and tested **but not deployed** — see [Deployment status](#deployment-status).

Call `POST /check` or `POST /verify` and you get one of five verdicts: `verified`, `altered`, `disputed`, `likely_match`, `not_found`.

---

## Receipts (tamper-evident proof of registration)

`service/receipt.py` builds a small signed JSON per registration:

```
{
  "imprint_receipt": 1,
  "chain_id": 10143,
  "registry": "0x…",
  "watermark_id": "0x…61 bits",
  "signer": "0x…",
  "fingerprint": "0x…",
  "fingerprint_algo": "phash-dct-16x16-v1",
  "timestamp": 0,
  "block": 0,
  "tx_hash": "0x…",
  "passkey": {"qx": "0x…", "qy": "0x…"}
}
```

- Signed by the relayer (the key that paid the gas).
- On check, every field is cross-examined against the live registry: the fingerprint must re-hash with the ID to reproduce the EIP-712 challenge, the recorded signer must be re-derivable from the passkey public key, and the transaction hash must be looked up in the block the record claims. Change any field, at least one check fails.
- A receipt is **a convenience and tamper-evidence layer, not a new source of truth**: the registry on Monad remains the truth.

## Independent verification (no demo UI needed)

`imprint_verify.py` verifies any image *or* a registered ID without the web app:

```
python service/imprint_verify.py copy.png                    # fingerprint the copy, find the closest record
python service/imprint_verify.py copy.png --id 0x…           # check the copy against one specific ID
python service/imprint_verify.py copy.png --scan --json      # content scan, machine-readable output
```

Statuses: `verified`, `altered`, `disputed`, `likely_match`, `not_found`, `unsupported_version`, `error`. Exit code is 0 for `verified` and `likely_match`, 1 for every other status. The verifier fingerprints the input image, hashes it, and reads the live registry (`--registry`, `--rpc`, `--chain-id`, `--algo` and `--max-records` override the defaults).

---

## The registry — trust model, scaling

An append-only table of `id → {signer, fingerprint, timestamp, block}`. Anyone can read everything (including enumeration), no one can change anything. That makes it:

- **Anti-squatting**: if you *don't* have the ID, you can't pre-register it. The ID is embedded in the marked PNG before it is released (claim hold), and the contract rejects the same ID twice.
- **Trustless to read**: a malicious read node can only *omit* a record, and that is caught by an offline checklist (independent verification section). It cannot invent one.
- **Latency-bound**: a straight RPC round-trip is the cost of a single `recordOf`. Anything that touches the chain is ~0.3–5 s; anything that does not (the index at [Scaling](#scaling--what-is-and-isnt-measured)) is instant.

### Scaling — what is and isn't measured

The full analysis is in [`docs/scaling.md`](docs/scaling.md); TL;DR:

| Lookup | as scan grows | projected at 1M records |
|---|---|---|
| CPU linear scan (`bench_lookup.py`) | 0.77 ms @ 10k → 81.8 ms @ 1M | ~0.8 s |
| BK-tree (hyperplane), every radius | slower than the linear scan | — |
| **RPC round-trip for a direct ID** (`bench_verify.py`, live testnet) | 0.82 s fetch + ~0.01 ms compare for 114 records | ~68 min for a full scan by fetch |

So **an authenticated, off-chain fingerprint index is not yet worth its trust tax** — the registry read is what dominates today (1k = ~4.1 s, 10k = ~41 s). The design is: an authenticated, index-of-hashes sent to the contract in batches (delayed unless you're scanning the whole registry), making the index *opt-in* and *verifiable*, not plugged into a foreign "checksum index". The choice is a gate in the roadmap: **deploy the index only if measured latency justifies it.**

---

## Deployment status

- **Current contract (live):** [`0xf4a792ddb0c83Bdf1Ed2E1220B197760d821396c`](https://testnet.monadvision.com/address/0xf4a792ddb0c83Bdf1Ed2E1220B197760d821396c), chain 10143, deployed at block `69296432`, source verified by Sourcify. The deployed bytecode is the contract *as of commit `7e2ec49`* — which already includes the `recordsPage` overflow clamp (commit `48f0c38` predates the deployment).
- **Retired:** [`0xF88Ab1f3E04Df4C8A6d5EAf3a64E3AC55095b664`](https://testnet.monadvision.com/address/0xF88Ab1f3E04Df4C8A6d5EAf3a64E3AC55095b664). It predates the enumerable registry (`count`/`recordsPage` revert on it) and holds no active path. A stale page render may still show it; `deployments/monad-testnet.json` records both addresses and which one is current. Do not register against the retired address.
- **Source-only (implemented + tested, not redeployed):** the on-chain dispute feature (`disputeDuplicate`, `hammingDistance`, `isDisputed`, `disputeOf`, `DISPUTE_MAX_DISTANCE` — commit `7b5a009` and later; emitted event `RecordDisputed`). The `recordsPage` clamp and the disputes are part of the same `contracts/src`; `deploy/verify_deployment.py` reports the drift objectively and reproducibly (it compiled the source ABI and checks each selector against the deployed runtime bytecode — currently 5 of 29 functions are MISSING, all dispute-related). The API never asks for pages larger than 100, and the dispute verdict is computed by the service at check time, so this is a feature awaiting a funded key + review decision, not a missing security control. See [`docs/deployment-review.md`](docs/deployment-review.md).

---

## Evidence

All of it is in `phase1/results/*.json` and `phase2/results/*.json` (every number below is pulled from one of those files and reproduced by the commands in [Run it yourself](#run-it-yourself)). **The phase-1 set is real photographs, the phase-2 set is synthetic (label is committed in every result file).**

### The 24-photo real set (phase 1, `phase1_Q.json`)

- **Watermark decode:** 24/24 decode the embedded ID at normal sharing (mean decode rate 1.0). On unmarked images, 0/24 produce a watermark (false positive).
- **Unrelated image distance:** 102–128 bits, median ≈ 128 (276 pairs). The hash measures *how much the pixels changed*, not visual similarity, so unrelated photos are far apart at this scale.

### The 40-photo real held-out set (`heldout.json`)

- **Sharing (240 checks):** 3 wrongly-altered (1.25% — heavy re-encode + low-texture photo). A re-encode *never* comes out as `verified` when it's not.
- **Edits (200 checks):** 1 wrongly-verified (0.5%) — **the one edit the pipeline thought was re-encoding**. An edit never comes out as `altered` by surprise.
- **Unrelated (780 pairs):** 0 false positives; closest pair 88 bits apart.

### Hard transforms and attacks (24-photo set, `phase1_extra.json`)

| Transform / attack | result |
|---|---|
| Horizontal flip | 24/24 still decode. |
| Grayscale | 24/24 still decode. |
| 2× upscale then JPEG q70 | 24/24 still decode. |
| 5° rotation | 0/24 decode — a rotation breaks the DCT grid; the fingerprint (not the watermark) is what still matches. |
| Paste edit, 10% of the image | distance min 30 / median 50 bits → **`altered`** (never `verified`). |
| Paste edit, 25% of the image | distance min 54 / median 75 bits → **`altered`** (never `verified`). |
| Re-watermarking a registered image | the *second* payload wins 24/24 — but the perceptual fingerprint still matches the original (median 2 bits, max 6), which is exactly why the fingerprint and not the watermark is the registry key. |

### The synthetic 1,400-image investigation (phase 2, `investigate.py` → `investigate.json`)

Sweep across 7 content classes (texture, noise, gradient, symmetry, portrait-ish, shapes, low-contrast TV test pattern), 200 images each. This is the largest single measurement in the repo and the basis for the honest limits of the "tell apart an edit" claim:

- Wrongly-classified (`>16`) by class: shapes **0/600**, portrait-ish **0/600**, noise **142/600**, gradient **537/600**, symmetry **600/600**, low-contrast **500/600**, texture **578/600**. The symmetry/low-contrast/texture classes are a *confounder*: a heavy re-encode of flat content pushes the phash past 16 even though the image is unchanged (in the eval run, 100% of those still decoded the ID). The watermark, not the phash, is what says "same image" there — which is exactly why the recommendation below is to trust a decoded ID; that change is **not** in the production verifier yet.
- **Unrelated distance scales dramatically**: 979,300 cross-pairs, minimum distance **2 bits**, 57 pairs ≤ 16, 23 pairs ≤ 10, first collision at threshold 9. The 40-photo set was a sample; at 1,400 images the *same content composition* produces flat (non-photographic) collisions. Not a bug — a documented limit.
- The recommendation from this investigation (in [`docs/false-rejections.md`](docs/false-rejections.md)): **do not raise the thresholds**; instead treat a correctly-decoded ID as the authoritative signal (an "edited" copy that decodes the ID is the *same* registered image with heavier re-encoding), and reserve "altered" for edit-scale drift. That decision rule is **implemented in the report, not in the production verifier** — it changes the semantics of the `altered` verdict and is a product decision, not a code fix.

### The synthetic evaluation runs (phase 2)

`evaluate.py` + `corpus.py` (torchvision seed banks: 200 images/category, ~500 images, 7 classes; leakage guard: identical content across train/test is a fatal `LeakageError`)

- `eval_Q.json` (14/split): 36/84 and 42/84 wrongly-altered on synthetic categories with *flat-content overlap*; edits wrongly verified **1/175** and **0/175**; unrelated min **80/64**.
- `eval_Q5.json` (35/split): 94/210 and 87/210 wrongly-altered on the same flat-content *overlap-prone* categories, **100% of which had their ID decoded** (i.e. the *watermark* said "this is the same image"); edits wrongly verified **1/175** and **0/175**; unrelated min **80/64**.

Both runs exist so *any* report can be cited without the other; they never release binary results. Thresholds are **unmodified** (16/24/10). Dataset splits and leakage checks are documented in [`docs/evaluation.md`](docs/evaluation.md); the leakage between eval and held-out sets is the *one overlapping real photo* and one outlier — both disclosed in the docs.

### Cost and speed (live, `phase1/results/batch_bench.json`)

| Measurement | value |
|---|---|
| 60 registrations, total wall time | 413.6 s |
| Register (median / p90) — Mark RPC + submit + wait | 4.81 s / 5.42 s |
| Chain (median) — broadcast → confirmation | 1.59 s (burst of 20: 7.36 s, 12 blocks) |
| Gas (median) @ 102 gwei | 173,420 (~0.0177 MON per registration) |
| Total spent | 1.06 MON (60 regs) + 0.41 MON (burst of 20) |

### What isn't measured yet

- Real WhatsApp/Telegram/screenshot/social actual delivery (the `phase2/channels.py` harness is ready, captures are git-ignored, inputs pending).
- AI / generated-ish detection on the perceptual fingerprint.
- `bench_verify.py` is run on the live testnet (fetch 0.82 s, compare ~0.01 ms for 114 records) — it records **1k = ~4.1 s, 10k = ~41 s** scan projections from that run. The synthetic `bench_lookup.py` numbers are CPU-only and labeled as such.
- The `SimilarityCost.sol` contract-level gas measurement of exhaustive Hamming search.

---

## API

All endpoints are defined in `service/app.py` and return JSON. Uploads are `multipart/form-data`. The Next.js web app is a thin client for them; reads hit the RPC with `eth_call` and the only write path is the relayer used by `/register`.

| Method + path | Purpose |
|---|---|
| `GET /health` | Liveness, payload bit length, and the current busy count. |
| `GET /config` | Chain id, registry address, fingerprint algorithm/bits, thresholds, claim TTL. |
| `GET /status` | Launch diagnostics: RPC reachable, chain id matches, registry deployed (with count), relayer configured and funded. |
| `POST /mark` | Upload an image; returns its `watermark_id`, `fingerprint`, chosen `strength`, self-test result and an opaque claim token. The marked PNG is withheld (see claims). |
| `GET /claim?token=` | Reveals the marked PNG **only after** its ID is on chain (`409` until then). |
| `POST /check` | Upload a copy; returns the hidden ID (if present) and the fingerprint, with no registry lookup. |
| `GET /challenge?watermark_id=&fingerprint=` | The EIP-712 challenge the passkey signs. |
| `GET /signer?qx=&qy=` | Registry signer address derived from a P-256 passkey public key. |
| `POST /register` | Submit `{watermark_id, fingerprint, qx, qy, auth, claim}`: squatting guard (near-duplicate by another signer → `409`), rate/daily limits, relay the record, return the record + a signed receipt (+ the marked image if the claim matches). |
| `POST /receipt/verify` | Check a signed receipt JSON against the live registry. |
| `POST /verify` | Upload a copy; the five-verdict result (`verified`/`altered`/`disputed`/`likely_match`/`not_found`) with the nearest record and any earlier dispute. |
| `GET /record/{watermark_id}` | One record, or `404`. |
| `GET /records?limit=&signer=` | Recent registrations, or all registrations by one signer (the "my work" view). |
| `POST /stress` | Upload an image (+ optional donor); re-run the 15-case robustness matrix and report whether the input actually carries a registered mark. |

Errors: `400` bad upload, `404` unknown claim/record, `409` duplicate or not-yet-registered, `413` file over 30 MB, `422` bad hex, `429` rate/daily limit (with `Retry-After`), `503` busy.

### Limits

Enforced in `service/limits.py`, surfaced in `Retry-After` headers, and every value is configurable (`0` disables). Defaults:

| Limit | Default |
|---|---|
| `IMPRINT_PER_IP_HOUR` registrations per IP per hour | 12 |
| `IMPRINT_PER_IP_ATTEMPTS_HOUR` `/register` attempts per IP per hour | 30 |
| `IMPRINT_GLOBAL_DAY` registrations per day, shared — the relayer's budget | 150 |
| `IMPRINT_HEAVY_PER_MIN` mark/verify/stress requests per minute | 20 |
| `IMPRINT_MAX_BUSY` concurrent heavy requests | 2 |
| `IMPRINT_MAX_CLAIMS` pending claims held in memory | 2000 |
| Max upload size | 30 MB |

The service is otherwise **stateless** apart from the bounded in-memory claim store and a short-lived `count()` cache (`IMPRINT_COUNT_TTL`), and it has no registry write path beyond the relayer.

---

## Configuration (`.env.example`)

Every value is optional; the defaults point at the **live Monad testnet**, so a bare checkout runs read-only. Copy to `.env` to change anything.

| Variable | Default | Purpose |
|---|---|---|
| `IMPRINT_RPC` | `https://testnet-rpc.monad.xyz` | Chain RPC endpoint. |
| `IMPRINT_CHAIN_ID` | `10143` | Expected chain id (checked in `/status`). |
| `IMPRINT_REGISTRY` | `0xf4a792dd…` | Registry contract to read/write. |
| `IMPRINT_DEPLOY_BLOCK` | `69296432` | First block scanned for records. |
| `IMPRINT_EXPLORER` | `https://testnet.monadvision.com` | Explorer base for record links. |
| `IMPRINT_COUNT_TTL` | `10` | Seconds to cache `count()` to spare the RPC. |
| `IMPRINT_RELAYER_KEY` / `IMPRINT_RELAYER_KEY_FILE` | *(none)* | Relayer that pays registration gas. Needed only for `/register`; prefer the file form so the key stays out of the environment. |
| `IMPRINT_PER_IP_HOUR` / `IMPRINT_PER_IP_ATTEMPTS_HOUR` | `12` / `30` | Per-IP success / attempt limits. |
| `IMPRINT_GLOBAL_DAY` | `150` | Shared daily registration cap. |
| `IMPRINT_HEAVY_PER_MIN` / `IMPRINT_MAX_BUSY` | `20` / `2` | Heavy-endpoint rate and concurrency. |
| `IMPRINT_TRUSTED_PROXIES` / `IMPRINT_XFF_HOPS` | `*` / `1` | Which `X-Forwarded-For` hop is the client. |
| `IMPRINT_CORS_ORIGINS` | `*` | Browser origins allowed. |
| `IMPRINT_CLAIM_TTL` / `IMPRINT_MAX_CLAIMS` | `900` / `2000` | Pending-claim lifetime and memory bound. |
| `IMPRINT_INDEX` | `0` | `1` enables the BK-tree fingerprint index (measured no faster at these radii — see [Scaling](#scaling--what-is-and-isnt-measured)). |
| `IMPRINT_LOW_BALANCE_WEI` / `IMPRINT_STATUS_SHOW_BALANCE` | `5e17` / off | Relayer-balance warnings in `/status`. |

`phase2/channels.py` also honours `IMPRINT_CHANNEL_ROOT` (default `phase2/real`) for where it writes git-ignored real-channel captures.

---

## Run it yourself

### Install

```
pip install -r requirements.txt        # service + phase1/phase2 harnesses
cd web && npm install                   # Next.js demo
```

### Tests — all of them

```
forge test                              # contracts  (28 passed)
python -m pytest -q service             # service     (90 passed)
python -m pytest -q phase2              # phase 2     (12 passed)
cd web && npm run lint && npm run typecheck
```

### Reproducing every number in this README

```
python service/e2e_testnet.py [image]        # live end-to-end (writes a real testnet record)
python phase1/robustness.py --images 24      # 24-photo real set -> results/phase1_Q.json
python phase1/heldout.py                     # 40-photo held-out set -> results/heldout.json
python phase2/evaluate.py                    # synthetic, leak-checked report -> eval_Q.json
python phase2/investigate.py                 # 1,400-image false-rejection sweep
python phase2/channels.py init               # scaffold phase2/real/ for real captures
python phase2/channels.py validate --manifest phase2/real/manifest.json
python phase2/channels.py run                # offline fingerprinting of captured files
python phase2/channels.py summarize --out results/real_check.json
python service/bench_lookup.py               # CPU linear + BK-tree scan (synthetic)
python service/bench_verify.py               # live-testnet scan-latency projection
python deploy/verify_deployment.py           # source-vs-deployed drift (currently 5 dispute funcs)
```

All scripts are documented and deterministic, and every number quoted above comes from one of their JSON outputs; re-running them refreshes it. The web app's `POST /stress` and `/verify` reproduce the same harness live. (`service/stress.py` is the library behind `POST /stress`, not a CLI.)

---

## Repo layout

```
contracts/       Solidity registry + tests (forge)
service/         Python API (FastAPI), fingerprint, verdict, receipt, claims
phase1/          real-photo evaluation + results (JSON) + heldout set
phase2/          synthetic evaluation, investigate sweep, channels harness, results
web/             Next.js demo (register/verify/my-work/receipt/stress/evidence/r/[id])
docs/            evaluation, fingerprint, enforcement, verifier, scaling,
                 onchain-duplicates, c2pa, merkle-batch, deployment-review,
                 real-world-testing, validation, false-rejections
deploy/          deployment manifest + verify_deployment.py
```

---

## Roadmap

**In-repo, code-complete, awaiting a decision:**
- Deploy the on-chain dispute feature (funded testnet key + review of [`docs/deployment-review.md`](docs/deployment-review.md); Option A/B decision: register a second address list or move to a new address).
- Apply the `false-rejections.md` decision rule (decoded-ID authoritative) to the production verifier — a product call, not a code fix.
- A content-adaptive secondary hash as a *new algorithm version* (records already carry `fingerprint_algo`).

**External blockers (people/phones/models, not code):**
- Real WhatsApp/Telegram/screenshot captures via `phase2/channels.py` (harness ready).
- A large AI-generated / generated-ish held-out set.
- A paying-creator validation pilot — see [`docs/validation.md`](docs/validation.md).

---

## Known limitations — what this does NOT do

- It does not prevent a *screenshot* or a copy being taken at rest; it *identifies* a later copy of a *registered* image.
- It does not prove authorship or ownership; it proves "this signer registered this image at this time" (signature + timestamp).
- It is **testnet-only** and the registry is reset at deployment. Not audited.
- The watermark is weaker on flat/low-texture content and can be cropped out if the watermark region is removed.
- `disputeDuplicate` etc. are **source-only** on the live deployment; the service's `disputed` verdict is computed off-chain today.
- The `altered` verdict is not and never will be "AI edit detection"; it is "these two images are more than 24 bits apart under this hash recipe" — an *edit* that happens to stay within 24 bits on low-texture content will verify. That's a documented limit, see [`docs/evaluation.md`](docs/evaluation.md).
- The proof of work is a crawl; there is no snapshotting of the global registry and no cross-chain mirror.

---

## Security model, step by step

1. **No trust in the server.** The contract is the truth; the service is a convenience, the receipt is tamper-evidence, and the web app is a thin client. Anyone can verify independently (`imprint_verify.py`).
2. **No ownership, no upgrade, no fee, no pause.** An attacker who compromises the relayer key cannot change, delete or front-run records — the contract has no such path. The most they can do is refuse to relay (a coordination problem, not a security one).
3. **No identifiable data on chain.** Only a 61-bit pseudorandom ID, a fingerprint (a hash), a P-256 public key and a timestamp. The relayer the service pays from is a single testnet wallet with a daily cap.
4. **The front-running window is closed by the claim hold** (marked bytes never leave the server before the ID is on chain).
5. **Passkey = P-256 verification** through Monad's precompile at `0x0100`; the recorded signer is `uint160(uint256(keccak256(abi.encode(qx, qy))))`. Nothing server-side can mint a signature.

Threat model and countermeasures are fully enumerated in [`docs/enforcement.md`](docs/enforcement.md) and [`docs/verifier.md`](docs/verifier.md). Any exploit found, the fix is a new `contracts/src` revision plus a new manifest entry (the deployment tooling exists for this).

---

## Contributing

PRs welcome. The bar: every claim in this README must remain reproducible by a command in this repo. Add a result JSON, add the doc, add the test. Discussions on [`docs/enforcement.md`](docs/enforcement.md) and [`docs/scaling.md`](docs/scaling.md) are open.