# Scaling lookup and verification

How the registry behaves as it grows, measured, and what would actually have to
change. Command: `python service/bench_lookup.py` (reproducible, seeded).

## The lookup itself is not the bottleneck

The service compares a 256-bit fingerprint against stored ones with a Hamming
distance (a 256-bit XOR popcount), optionally via the BK-tree in
`service/index.py`. Measured CPU time per single query (median, random 256-bit
fingerprints, seed 1234):

| records | linear r10 | linear r16 | linear r24 | BK-tree r10 | BK-tree r16 | BK-tree r24 |
|---|---|---|---|---|---|---|
| 10,000 | 0.77 ms | 0.76 ms | 0.72 ms | 1.02 ms (1.3x) | 2.24 ms (2.9x) | 3.40 ms (4.8x) |
| 100,000 | 7.4 ms | 8.5 ms | 9.7 ms | 11.9 ms (1.6x) | 32.4 ms (3.8x) | 54.8 ms (5.7x) |
| 1,000,000 | 81.8 ms | 82.3 ms | 75.5 ms | 84.2 ms (1.0x) | 311.9 ms (3.8x) | 570.5 ms (7.6x) |

Two conclusions:

- **A linear scan is cheap** — ~82 ms at a million records. The BK-tree is
  **slower at every radius** (parenthesised factor is BK ÷ linear), because the
  search radius (10–24 of a 256-bit diameter) is too large relative to the tree
  for the triangle inequality to prune much. This is why `IMPRINT_INDEX`
  defaults off; the index is kept correct and tested for pathological future
  clustering, not because it wins today.
- Even at 1M records the distance computation is not the wall. **The wall is
  reading the records.**

## The real wall: enumeration over RPC

`recordsPage(offset, limit)` caps `limit` at what a caller asks for; the service
and the standalone verifier read the registry in pages of 100 and compare
locally. That is *N/100* RPC round-trips:

| records | `recordsPage` calls (limit 100) |
|---|---|
| 10,000 | 100 |
| 100,000 | 1,000 |
| 1,000,000 | 10,000 |

At ~100 ms per round-trip, a million-record scan is on the order of **tens of
minutes per verification**, dominated by latency and JSON decoding, not by the
Hamming math. The `/records` and `/status` endpoints and the verifier's
`--max-records` guard already bound this, but bounding it is not the same as
solving it.

## Options, evaluated

| Option | Helps writes | Helps reads at scale | Cost / risk | Verdict |
|---|---|---|---|---|
| **BK-tree** (built) | n/a | No (measured slower) | none | keep opt-in, off |
| **Merkle batch commitments** | marginally (anchors many per tx) | No — you still need the leaf set; proofs must be served by someone | complicates the append-only API and the "enumerate with plain calls" property | not now |
| **Authenticated index** (Merkle/Verkle over records) | No | Inclusion only; a **nearest-neighbour** query is not an inclusion query | build + proof service | not sufficient alone |
| **Verifiable indexer** (off-chain index + on-chain commitment) | No | **Yes** — advertise the bottleneck | new trust surface (liveness), needs proofs to stay trustless on integrity | the honest path, later |

The registry's defining property — *anyone can enumerate every record with plain
`count`/`recordsPage` calls, no indexer* — is what makes it independently
verifiable and admin-free. A Merkle batch weakens that property for a write-cost
saving that does not matter here (a single registration is ~173k gas / 0.0177
MON, measured in `phase1/results/batch_bench.json`). So batching is not
justified by measurement.

## Recommendation

1. **Keep** the one-record-per-transaction append-only registry and the linear
   scan. At realistic sizes (hundreds to low thousands) it is milliseconds.
2. **Do not** enable the BK-tree; the measurement says it loses.
3. If verification must scale to 10^5+ records, add — as a **separate,
   additive** component, not a replacement — an **off-chain fingerprint index
   whose root is committed on chain by anyone**, so a client can ask for a
   nearest-candidate and a proof, and check it against the committed root. This
   keeps integrity trustless (proofs) while accepting liveness trust (someone
   must publish the index). It is directly justified by the measured wall:
   enumeration is the cost, and an index eliminates enumeration.
4. Any such addition must be justified by a **new measurement of the end-to-end
   read path** (fetch + proof verify) showing it beats a plain scan — not by
   assuming a tree is faster. This repository's habit is to measure first.
