# The enforcement boundary

This document states, precisely, what Imprint enforces and where. The point is
to avoid the common trap of a soft binding looking like a hard guarantee.

## What the contract enforces

`ImprintRegistry.sol` enforces exactly one thing: **a registration carries a
valid signature over `(watermarkId, fingerprint)` bound to this chain and
contract.** A passkey (P-256 via Monad's precompile) or an EIP-712 key must have
signed the ID and the fingerprint together. It also enforces that an ID is
registered once (`AlreadyRegistered`). It does not look at the image, does not
compare fingerprints, and has no owner, allowlist, fee, pause or upgrade path.

Consequences:

- Nobody can register an ID **in someone else's name** without their key.
- The relayer cannot lie about the fingerprint: it is inside the signed message.
- **Nothing stops a caller from registering a near-duplicate of an existing
  image** if they sign it themselves. The chain has no opinion about similarity.

## What the service enforces (policy, not consensus)

The FastAPI service adds convenience rules on top:

- **Squatting guard.** Before spending gas, `/register` refuses an image whose
  fingerprint is within `T_DUP` (10 bits) of an earlier record by a *different*
  signer, returning `409 near_duplicate`. Re-registering your own image is
  allowed.
- **Dispute verdict.** `/verify` (and the standalone checker) mark a later
  look-alike as *disputed* regardless of how the record got on chain.

Because these live in the service, **a direct contract call bypasses the guard.**
This is a knowing trade-off in favour of an uncensorable, admin-free registry.
The mitigation is visibility, not prevention: the situation is always
reconstructible from public chain data.

## The mark-before-claim race, and its fix

The hidden ID is readable from a marked image by anyone (the decoder is public).
If `/mark` returned the marked pixels before registration, an observer could read
the ID and register it first.

Fix: `/mark` withholds the pixels and returns only an opaque, single-use,
TTL-bounded **claim token** (`service/claims.py`). The pixels are revealed only
when the ID is on chain:

- `/register` with a matching claim returns the image and burns the token; or
- `/claim?token=` returns the image **only if** the ID already exists in the
  registry.

So there is no marked file to front-run. Claims are in-memory and expire
(`IMPRINT_CLAIM_TTL`, default 900 s); a restart drops pending marks, which the
client simply re-creates. This closes the ID-leak window; it does not change the
fact that the registration itself is permissionless.

## On-chain dispute (source; pending redeploy)

`disputeDuplicate(earlierId, laterId)` lets **anyone** record that a later record
is within `DISPUTE_MAX_DISTANCE` (10 bits) of an earlier one:

- both records must exist and be ordered (`earlier` at a strictly lower block);
- the distance is checked on chain via `hammingDistance`;
- it is non-destructive (neither record is altered) and has no admin;
- each later ID can be disputed once, so spam cannot bury a record;
- it emits `RecordDisputed` and is queryable via `isDisputed` / `disputeOf`.

It is **not deployed** on the current testnet registry. It makes a dispute
public and trustless; it does not remove the record and does not prevent the
duplicate from having been registered.

## What Imprint never claims

- It does not prove authorship or that the image is authentic.
- "Not found" is not "fake".
- The watermark is removable and crop/rotation-fragile; the fingerprint carries
  the fallback, and it fails on genuine content edits by design.
