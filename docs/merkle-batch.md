# Merkle-batched registration: evaluation (not implemented)

**Status: design only, deliberately not implemented.** Registrations go on chain
one per transaction today. This note explains why batching is not warranted at
the current scale, and what it would take.

## The idea

Instead of one `registerSigned`/`registerPasskey` transaction per image, a
submitter collects many `(watermarkId, fingerprint)` registrations, builds a
Merkle tree, and anchors just the **root** in one transaction (plus the count).
A verifier claims inclusion with a Merkle proof against the root. This is the
standard way to amortize per-transaction overhead when you have many leaves.

## Why it is not worth it here (measured)

From `service/batch_bench.py` (Monad testnet, one run):

- A full registration through the product path costs **~173,420 gas ≈ 0.0177 MON**
  and confirms in **~1.6 s** send-to-receipt.
- The dominant cost is per-transaction base cost plus the single `SSTORE`, not
  the marginal cost of one more record.

A Merkle batch would remove most of the per-image base cost, but:

- it adds **calldata for every proof** at verify time (or a full leaf reveal),
- it introduces a **submitter trust/UX problem**: until the root lands, no single
  image has a record; who batches, and when, becomes a policy,
- it changes the contract's public API (`recordsPage`, `recordOf`) that the
  standalone verifier and the frontend read directly.

At Monad's fee level and sub-2-second confirmation, the honest conclusion is
that batching optimises a cost that is already negligible, at the price of a
worse, more centralized UX. The one-tx-per-image design also keeps the
"anyone can enumerate the whole registry with plain calls, no indexer" property,
which a Merkle scheme weakens.

## If it were implemented

The lowest-risk shape would be an **optional** second contract or method that
anchors a Merkle root of pending registrations, leaving the existing per-image
path untouched, and an optional proof-carrying read path. It should be justified
by a real cost measurement (as above) showing the batch is cheaper end to end,
including proof calldata, before any code is written.

Until that measurement exists, this stays a plan, not a feature.
