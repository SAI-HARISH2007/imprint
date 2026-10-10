# The Imprint fingerprint: `phash-dct-16x16-v1`

This is the normative specification of the 256-bit perceptual fingerprint Imprint
stores on Monad. The reference implementation is `service/fingerprint.py`. Any
independent reimplementation that follows these steps reproduces the same bits,
which is what makes a record written today checkable forever.

## Algorithm id and versioning

- Algorithm id: **`phash-dct-16x16-v1`**
- Version: **1** (`fingerprint.VERSION`)
- Output: 256 bits = 64 lowercase hex characters, no `0x` prefix
- On chain: stored as `bytes32`, so the first hex character is the most
  significant nibble of the first byte.

Every registration receipt carries a `fingerprint_algo` field, and both
`GET /config` and `POST /verify` expose the algorithm id. A receipt written
before the field existed is treated as version 1. The standalone verifier
refuses to interpret a record whose algorithm id it does not know
(`unsupported_version`), so a future change cannot silently misread old records.

## The recipe

Given an input image:

1. **Grayscale.** Convert to 8-bit grayscale with the ITU-R BT.601 luma
   transform (Pillow: `Image.convert("L")`).
2. **Resize.** Resize to exactly **64x64** pixels with Lanczos resampling,
   ignoring aspect ratio (Pillow: `Image.Resampling.LANCZOS`).
3. **DCT.** Treat the 64x64 plane as a `float64` matrix and apply a type-II
   discrete cosine transform on axis 0, then axis 1
   (`scipy.fftpack.dct`, defaults `type=2, norm=None`).
4. **Low frequencies.** Keep the top-left **16x16** block of coefficients. The
   DC term `[0,0]` is included.
5. **Median.** Compute the median of those 256 coefficients.
6. **Bits.** Emit `1` where a coefficient is **strictly greater** than the
   median, else `0`, scanning row by row (left to right, top to bottom).
7. **Encoding.** The 256 bits form a big-endian integer, rendered as 64
   lowercase hex characters, zero padded.

Parameters: `HASH_SIZE = 16`, `HIGHFREQ_FACTOR = 4`, `IMAGE_SIZE = 64`.

## Hamming distance

`distance(a, b)` is the number of differing bits — the population count of the
XOR of the two 256-bit integers. It is a true metric over the 256-bit space.
The contract's `hammingDistance(bytes32, bytes32)` computes the same value
on chain. The service thresholds are:

| Name | Value | Meaning |
|---|---|---|
| `T_MATCH` | 16 | at or below: consistent with the registered image |
| `T_NEAR` | 24 | at or below: a likely copy when the mark is lost |
| `T_DUP` | 10 | at or below: a duplicate for the registration guard and disputes |

## Test vectors

Deterministic pattern `pattern(w, h)`: pixel `(x, y)` = `RGB((7x+13y) % 256,
(3x+5y) % 256, (x XOR y) % 256)`. Produced with imagehash 4.3.2, numpy 2.5.3,
scipy 1.18.1, Pillow 12.3.0.

| Input | Fingerprint (hex) |
|---|---|
| `pattern(64, 64)` | `8ccf81112cff6607488e1afb0cce5efbfc40391123de7e0150ef55aaff08107b` |
| `pattern(128, 96)` | `a40408fbe40408ff5eb4f0ff5c04b1ff8b1554ab11b6572b13e4ff914bc4aa8d` |
| `pattern(37, 53)` | `863300046ebfd001173d11433ff9f0062ffe580a2775ad575aea7c2ba95faa55` |
| horizontal gradient 256x256 | `8000000000000000000000000000000000000000000000000000000000000000` |

These vectors are asserted in `service/test_fingerprint.py`, which also checks the
reference recipe bit-for-bit and cross-checks the distance against imagehash.

## Reproducibility limits

Bit-for-bit equality holds when the same numeric libraries are used (see the
pins in `requirements.txt`). A coefficient that lands exactly on the median can
flip across BLAS/FFT builds; this is rare and would shift the distance by one or
two bits, well inside the match thresholds.
