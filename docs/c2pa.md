# C2PA interoperability: evaluation (not implemented)

**Status: design only, deliberately not implemented.** No C2PA code ships in this
repository. This note records the evaluation so the gap is explicit rather than
implied.

## Why Imprint cares

[C2PA](https://c2pa.org/) content credentials are the established provenance
container. A C2PA manifest can carry a **soft binding** — a fingerprint and/or an
invisible watermark — whose whole purpose is to recover provenance after the
hard-binding metadata is stripped. Imprint's ID and fingerprint are exactly such
soft bindings, so a C2PA manifest could carry the Imprint watermark ID and the
Monad registration transaction as an assertion, and an Imprint-aware verifier
could read it.

## What integration would require

1. **A signing identity.** C2PA manifests are signed with X.509 certificates and
   validated against a trust list. Imprint is currently keyless-relative-to-C2PA
   (a passkey + a relayer). Mapping passkey identity to a C2PA claim generator is
   non-trivial and would drag in certificate issuance / hosting.
2. **The `c2pa-python` (or Rust) toolchain** plus a way to embed and re-read
   manifests without altering pixels enough to move the fingerprint.
3. **A defined assertion shape**, e.g. a custom assertion
   `imprint.registration.v1 { watermark_id, chain_id, registry, tx_hash }`.

## Why it is not in this build

- It does not change the trust model: Imprint already works when metadata is
  stripped, which is the failure mode C2PA soft bindings exist to address. The
  metadata path is the *fragile* path; Imprint chose the durable one first.
- It needs a certificate/trust-list story that is out of scope for the build
  window and would not be exercised end to end honestly.
- The correct claim is that Imprint is **complementary** to C2PA, not a
  replacement, and that a soft-binding assertion is the natural next step.

If implemented, it must be tested against a real manifest and a real validator
before any claim is made. Until then, treat this file as a plan, not a feature.
