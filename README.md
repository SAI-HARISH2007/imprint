# Imprint

**Register an image with a passkey. A compressed, resized or screenshotted copy can still be checked against a public record on Monad, and an edited copy is told apart from a merely re-encoded one.**

Built for the Monad Metropolis hackathon, Track 4 (Trust, Identity and AI Infrastructure), answering the brief line *"provenance for generated media that survives re-encoding"*.

- Registry contract on Monad testnet: [`0xf4a792ddb0c83Bdf1Ed2E1220B197760d821396c`](https://testnet.monadvision.com/address/0xf4a792ddb0c83Bdf1Ed2E1220B197760d821396c) (chain 10143, source verified). The deployed bytecode is the contract as of commit `7e2ec49`. Two later additions in `contracts/src` — the `recordsPage` overflow clamp and the on-chain `disputeDuplicate` — are implemented and tested but **not redeployed** (the API never asks for pages larger than 100, and disputes are a source feature awaiting a redeploy).
- **The current contract is `0xf4a792…` (records answer `count()`; 114 registered at time of writing).** An earlier deployment, [`0xF88Ab1f3E04Df4C8A6d5EAf3a64E3AC55095b664`](https://testnet.monadvision.com/address/0xF88Ab1f3E04Df4C8A6d5EAf3a64E3AC55095b664), is **retired** — it predates the enumerable registry (`count`/`recordsPage` revert on it) and holds no active path. A stale page render may still show it; `deployments/monad-testnet.json` records both and which one is current. Do not register against the retired address.
- Live demo: https://imprint-ten-theta.vercel.app (API: https://sai-harish2007--imprint-api-api.modal.run)
- Demo video: *link added at submission*

## What it proves, and what it does not

Imprint proves that **a particular passkey registered this image at a particular time**, and whether a copy you hold is **still consistent with what was registered**.

It does **not** prove who made the image, that the image is real, or that it was never edited somewhere else. Anyone can register an image they did not make, so Imprint refuses to register an image that looks like one already on record by someone else, and the checker flags a later look-alike as *disputed*. **"Not found" means no record, not that the image is fake.** Imprint does not detect AI-generated content.

### Where the duplicate guard is enforced (be precise about this)

The near-duplicate refusal is a **policy of this service**, not of the contract. The contract stores whatever a validly-signed registration contains; it has no fingerprint comparison at registration. So a determined caller who signs directly and calls `registerSigned`/`registerPasskey` on Monad **can** register a near-duplicate, bypassing our `409`. The service is the convenience path that applies the guard; the chain is the record.

Two things reduce the gap, and one is honest about not closing it:

- The **checker** (service and `/verify`) reads the registry and marks a later look-alike as *disputed* regardless of how it got there, so the situation is at least visible to readers.
- The contract now includes a permissionless **`disputeDuplicate`** (source, pending redeploy) that records a public on-chain flag when two records are within 10 bits, non-destructively and with no admin.
- Neither prevents the registration from existing. This is a deliberate design choice — no owner, no allowlist, no censorship — and it is documented rather than hidden. See `docs/enforcement.md`.

## How it works

```
REGISTER                                   CHECK
image ──► hide a 61-bit ID in the pixels   any copy ──► read the ID (if it survived)
      ──► 256-bit perceptual fingerprint            ──► fingerprint how it looks now
      ──► passkey signs (ID, fingerprint)           ──► look up the ID on Monad
      ──► relayer submits; contract verifies        ──► compare fingerprints
          the P-256 signature on-chain              ──► one of five verdicts
      ──► marked image revealed only once the ID is on chain
```

The marked image is **withheld until the ID is on chain**. `/mark` returns only an opaque claim token; the pixels are returned by `/register` (or by `/claim`, but only after the ID exists in the registry). Otherwise anyone could read the hidden ID out of the file — the decoder is public — and register it first. See `docs/enforcement.md`.

Two independent signals, because they fail differently:

| Signal | What it is | Survives | Breaks on |
|---|---|---|---|
| Hidden ID | an invisible watermark ([TrustMark](https://github.com/adobe/trustmark), Adobe, MIT) carrying a random 61-bit ID | JPEG, resizing, screenshots, brightness, flips | heavy crops, rotation, deliberate removal |
| Fingerprint | a 256-bit perceptual hash of how the image looks | the same, and crops too | content edits (which is the point) |

The ID is an **exact lookup key** into the registry. The fingerprint is a **content-consistency check**, and a fallback when the ID is gone.

### The five verdicts

| Verdict | Condition |
|---|---|
| **Verified match** | ID found and on record, fingerprint within 16 bits of the registered one |
| **Altered** | ID found and on record, fingerprint further than 16 bits (edited or cropped) |
| **Likely match** | ID lost, but a registered fingerprint is within 24 bits. Lower confidence |
| **Disputed** | ID found, but a near-identical image (within 10 bits) was registered **earlier by a different signer** |
| **Not found** | none of the above. Not a claim that the image is fake |

Thresholds were chosen on a calibration set of 24 photos and then applied unchanged to a held-out set (see Evidence).

### What is on Monad

Per registration: `watermarkId`, `fingerprint`, `signer`, `timestamp`, `blockNumber`. No image, no metadata, no name. The contract has no owner, no upgrade path, no fee and no pause. First registration of an ID wins; duplicates revert. Anyone can enumerate the whole registry with plain calls (`count`, `recordsPage`), so no indexer is needed to verify independently.

### Registration receipts

Every successful registration also returns a **receipt**: a self-contained JSON that restates the record (ID, fingerprint, signer, block, transaction) plus the challenge the passkey signed and the relayer's own signature over all of it. `POST /receipt/verify` re-derives the passkey signer, checks the relayer signature, and matches every field against the live chain, so a holder can prove a registration later without trusting our database — and the `/receipt` page does this in the browser. Receipts are optional; the chain remains the source of truth.

### The fingerprint is a published specification

The 256-bit fingerprint is not an implementation detail: it is pinned as algorithm **`phash-dct-16x16-v1`** (version 1) in `service/fingerprint.py`, with the exact recipe written out, fixed test vectors, and an independent reference implementation checked against it (`service/test_fingerprint.py`). Every receipt carries `fingerprint_algo`, and `POST /config` and `POST /verify` expose the algorithm id, so a record written today stays interpretable if the algorithm ever changes. Full spec: `docs/fingerprint.md`.

### Verify without trusting our server

`service/imprint_verify.py` is a standalone checker. It reads your image with Pillow, computes the fingerprint with the published spec, and reads the registry straight from Monad with web3 — **it never calls the Imprint API and never trusts the server's verdict**. It does not decode the hidden watermark (that needs the TrustMark model, which it deliberately does not bundle); pass `--id` if you know it, or `--scan` to match by content.

```bash
cd service
python imprint_verify.py my_photo.png --id 0x… --json
python imprint_verify.py my_photo.png --scan
```

### Why a passkey, and why Monad

A creator should not need a wallet or a seed phrase to sign a registration. Imprint uses a **WebAuthn passkey** (fingerprint or face unlock). The browser signs an EIP-712 challenge that binds the ID and fingerprint to this chain and this contract; a relayer pays gas; **the contract itself verifies the P-256 signature through Monad's P256VERIFY precompile at `0x0100`** (OpenZeppelin's `WebAuthn` library). The relayer cannot register anything in someone else's name, and a visitor never needs testnet MON.

Monad gives us a public, append-only record anyone can check without trusting our server, cheap enough to anchor every image (measured below), fast enough that registration confirms while the user is still looking at the page, and native P-256 so the passkey story is on-chain rather than a backend conversion.

## API

The service is a single FastAPI app (`service/app.py`). Read-only endpoints need no key; only `/register` needs a relayer wallet.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness plus the payload width (`payload_bits`) |
| GET | `/config` | chain id, registry address, explorer, fingerprint algorithm + version, thresholds |
| GET | `/status` | RPC/chain-id/registry-code diagnostics, record count, relayer funded-or-not |
| POST | `/mark` | hide an ID in an image; returns a short-lived **claim token**, not the pixels |
| GET | `/claim?token=` | reveal a marked image, only once its ID is in the registry |
| POST | `/check` | raw read: the hidden ID (if any) and the fingerprint, no registry lookup |
| GET | `/challenge` | the EIP-712 challenge for a (ID, fingerprint) |
| GET | `/signer?qx=&qy=` | derive the address for a passkey public key |
| POST | `/register` | relay a passkey-signed registration; return the record, a receipt, and the marked image for a matching claim |
| POST | `/receipt/verify` | verify a receipt against the live chain |
| POST | `/verify` | check a marked image and its claimed record; returns the fingerprint algorithm id |
| GET | `/record/{watermark_id}` | the stored record for an ID |
| GET | `/records?limit=&signer=` | recent records, optionally filtered by signer |
| POST | `/stress` | re-run the robustness suite on a supplied image |

Registration is rate-limited per IP and globally, input is validated before any work, and the relayer is only asked to pay gas after the squatting check passes. All limits and the proxy trust model are environment-configurable; see `.env.example`.

## Evidence

Everything below is produced by scripts in this repository. Failures are reported on purpose.

### Does the mark survive ordinary sharing? (24 photos, `phase1/robustness.py`)

| Transform | Mark read | Median fingerprint distance (bits of 256) |
|---|---|---|
| JPEG q90 / q70 / q50 | 100% / 100% / 100% | 0 / 0 / 1 |
| JPEG q30 / q20 | 96% / 88% | 2 / 2 |
| Resize to 75% / 50% / 25% | 100% each | 0 |
| Messenger-style (cap 1600 px, q70) | 100% | 0 |
| Screenshot-like rescale | 100% | 2 |
| Brightness ±15%, contrast +15%, light blur, flip, grayscale | 96 to 100% | 0 to 2 |
| Upscale 2x then JPEG q70 | 100% | – |
| Crop 5% / 15% | 100% / 100% | 35 / 96 |
| **Crop 30%** | **0%** | 126 |
| **Rotate 5°** | **0%** | – |
| Foreign content pasted over 10% / 25% | 29% / 0% | 50 / 76 |

Unrelated images differ by at least 102 bits (median 128). No unmarked original read as marked (0/24). Ordinary sharing stays within about 12 bits; edits start near 30.

**Combined damage** (`phase1/combos.py`): resize 50% + JPEG q70 24/24; resize 75% + q50 24/24; **resize 50% + q50 22/24**; resize 25% + q60 9/12 on 1024 px images but 12/12 on 3000 px images. Harsh combinations fail on a minority of images, and small images fail more than large ones. When the mark is lost, the fingerprint usually still gives "likely match".

### Held-out check with the thresholds fixed in advance (40 fresh photos, `phase1/heldout.py`)

The thresholds above were chosen on the 24 calibration photos, then applied unchanged to 40 photos at mixed sizes and orientations that they had never seen.

| | Held-out result |
|---|---|
| Ordinary sharing, mark read (mean of 6 transforms) | 99% |
| Sharing copies wrongly called *altered* | 3 of 240 |
| Edits wrongly called *verified* | 1 of 200 |
| Unrelated image pairs called *likely match* | 0 of 780 (closest pair 88 bits apart) |
| Weakest transforms on fresh images | JPEG q20 80% read, brightness +15% 82% read, foreign paste 10% 42% read |

So the calibration numbers mostly held, and the places they did not (q20, strong brightening) are listed rather than hidden. One caveat found afterwards: the stock-photo source maps different seeds to a finite pool, and one of the 40 held-out images turned out to be the same photo as a calibration image, so 39 of the 40 were truly unseen. One photo in the held-out set is an outlier whose fingerprint drifts 18 to 30 bits under ordinary sharing; it accounts for most of the three false *altered* calls.

### Phase 2: a larger, leak-checked synthetic sweep (`phase2/`)

The two sets above are small. `phase2/` adds a reproducible, **offline** harness that
generates as many images as you ask for across seven categories (including hard
cases for a DCT hash: flat low-contrast and near-symmetric content) and enforces a
**leakage guard** before scoring — calibration and held-out images come from
disjoint seed banks, and a content-hash check proves no overlap. The committed run
(14 images per split) finds:

- **Clean negatives:** the closest *unrelated* pair is 100 bits of 256 even in the
  adversarial categories, with 0 false *near* and 0 false *duplicate* pairs, and
  0/70 edits wrongly called *verified*.
- **A real weakness, made visible:** synthetic texture drifts the fingerprint far
  more than real photos — 36–42 of 84 ordinary-sharing checks land as *altered*
  even though the watermark still decodes exactly. The 256-bit median threshold is
  brittle on flat content; the honest remedy is a content-aware threshold, not a
  looser one.
- The watermark itself degrades as phase 1 found: solid to q50/resize, weak at q20,
  gone past 25% crops or paste.

This complements, and does not replace, the real-photo sets; it is still
synthetic, the committed sample is small, and real messaging/screenshot transfers
remain unmeasured. Full method and numbers: `docs/evaluation.md`, `phase2/results/eval_Q.json`.

### Cost and speed on Monad (`service/batch_bench.py`)

- **60 registrations through the real product path** (mark, passkey assertion, relay, receipt), one after another: **0.0177 MON each** (173,420 gas at 102 gwei), **1.59 s median from send to receipt**. 1.06 MON for all 60.
- The register call as a whole took 4.8 s median in that run, most of it our own RPC round-trips; after trimming them, two later registrations took 2.9 s and 2.5 s end to end.
- **A burst of 20** sent at once from one key: all 20 landed, confirmed in 7.4 s across 12 blocks. 0.41 MON.
- One run, one day, testnet gas price. Numbers are what we saw, not a guarantee.

### Attacks we tried

- **Registering someone else's image first.** Re-marking an already marked image replaced its ID 24/24 times, so the mark alone cannot stop this. The fingerprint can: the re-marked copy stayed within 6 bits of the original. Imprint refuses such a registration (`409 near_duplicate`), and the checker marks a later look-alike as *disputed*. Re-registering your own image with your own passkey is allowed.
- **Copying the mark onto another picture.** Estimated the mark as (marked minus cleaned) and added it to a different image, at two gains, 5 pairs: **0 of 10 decoded**. The mark is content-adaptive. This is one simple attack, not a proof of safety.
- **Removing the mark.** TrustMark ships a remover and its decoder is open source, so a determined person can strip it. The fingerprint then gives "likely match" at best. We do not claim the mark is tamper-proof.

### Not yet measured

Real WhatsApp and Telegram transfers (the simulated versions are above), and real phone screenshots. These are listed as open until they are done.

## Prior art, and what is different here

This is not the first system to combine a watermark, a perceptual hash and a timestamp. [C2PA](https://c2pa.org/) defines soft bindings (fingerprints and invisible watermarks) exactly so provenance can be recovered after metadata is stripped; Adobe's TrustMark is the watermark we use; Digimarc and Tectra sell durable-provenance products built on similar ideas.

What Imprint adds is narrow and specific:

1. **An open, public registry on Monad** that anyone can read and verify without a vendor, with no admin keys.
2. **Passkey-native signing verified on-chain** through Monad's P-256 precompile.
3. **An explicit separation** of "same rendition" (verified) from "modified descendant" (altered) from "probable copy" (likely match), with "not found" never meaning fake.
4. **A published benchmark with the failures left in**, and a live stress page that reproduces it on any registered image.
5. **A squatting defense** — a service-enforced near-duplicate refusal, the *disputed* verdict from public chain data, and a permissionless on-chain `disputeDuplicate` (source, pending redeploy). The refusal is policy, not consensus; see "Where the duplicate guard is enforced".

A C2PA manifest could carry the Imprint ID and registration transaction as a soft binding; that interoperability is the natural next step, not a competitor.

## Limits

- Proves registration, not authorship.
- The near-duplicate refusal is enforced by the service, not the contract. A direct `registerSigned`/`registerPasskey` call can register a near-duplicate; the checker will still surface it as *disputed*. The on-chain `disputeDuplicate` makes this public but does not prevent it, and is not yet deployed.
- The mark is removable by someone who knows the library. Crops above about 20% and rotation defeat it.
- Thresholds were fixed on 24 photos and checked on 40; both sets are modest, and the held-out set has no AI-generated images yet.
- The relayer is a single testnet wallet with a daily cap. A real deployment would let apps run their own.
- Testnet only. Nothing here has been audited.

## Repository

```
contracts/   ImprintRegistry.sol (Foundry), tests, deploy script
service/     FastAPI image service and relay: mark, check, verify, stress, register, receipts
             plus fingerprint.py (spec), claims.py, index.py, imprint_verify.py (standalone checker)
web/         Next.js site: register, check, receipt, my work, stress test, evidence, record pages
phase1/      benchmark scripts and raw results (results/*.json)
phase2/      leak-checked synthetic evaluation harness (corpus, evaluate, results)
docs/        fingerprint spec, enforcement boundary, verifier, evaluation, scaling,
             on-chain duplicates, C2PA and Merkle-batch notes
deploy/      Dockerfile and build script for the API
deployments/ addresses and transaction hashes
```

### Run it locally

```bash
# contracts
cd contracts && forge test

# image service (Python 3.12)
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # optional; defaults point at the live testnet registry
cd service && uvicorn app:app --port 8000
# relayer key: put a testnet-only wallet in ~/.imprint/deployer.json (cast wallet new --json) or IMPRINT_RELAYER_KEY

# site
cd web && npm install && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

`service/e2e_testnet.py` runs the whole flow against the live registry with a software passkey. `service/test_service.py`, `service/test_hardening.py` (rate limits, input validation, receipts, the mark/claim race) and `service/test_fingerprint.py` / `test_claims.py` / `test_index.py` / `test_verifier.py` are the service tests, and `contracts/test` covers the contract (including the duplicate-scan gas measurement in `SimilarityCost.t.sol`). `phase2/test_corpus.py` tests the synthetic corpus and its leakage guard. `service/bench_lookup.py` reproduces the scaling numbers. The site checks itself with `npm run lint`, `npm run typecheck` and `npm run build`.

## Team

Sai Haresh Anand S ([@SAI-HARISH2007](https://github.com/SAI-HARISH2007)) and Dulam Seshivardhini ([@seshivardhini2006](https://github.com/seshivardhini2006)). All code was written during the Metropolis build window. AI coding tools were used throughout; every number above comes from a script in this repository that anyone can rerun.

## License

MIT. TrustMark is MIT (Adobe); OpenZeppelin Contracts are MIT.
