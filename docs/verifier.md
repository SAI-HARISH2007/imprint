# `imprint-verify`: checking without trusting the service

`service/imprint_verify.py` checks an image against the Imprint registry using
only your image and Monad. It does **not** call the Imprint API and does **not**
trust the server's verdict.

## What it uses

- Pillow to read the image
- `fingerprint.py` (the published spec) to compute the 256-bit fingerprint
- web3 to read the registry (`recordOf`, `count`, `recordsPage`)

Dependencies: Pillow, numpy, scipy, web3. It does **not** depend on TrustMark,
torch, or any Imprint server code.

## What it does not do

It does not decode the hidden watermark. Decoding needs the TrustMark model,
which the verifier deliberately does not bundle. So it cannot read the ID out of
an image on its own — you provide `--id`, or let `--scan` find the closest record
by content. Every result is labelled `"assurance": "content-only"`.

## Usage

```bash
cd service
python imprint_verify.py photo.png --id 0x<64 hex>        # check against a known ID
python imprint_verify.py photo.png --scan                 # closest record by content
python imprint_verify.py photo.png --id 0x… --json        # machine readable
python imprint_verify.py photo.png --scan --max-records 20000
```

Options: `--rpc`, `--registry`, `--chain-id`, `--abi`, `--algo`, `--max-records`.

## Statuses

| Status | Meaning |
|---|---|
| `verified` | content within `T_MATCH` (16) of the named record, no earlier look-alike |
| `altered` | within `T_NEAR` (24) but beyond `T_MATCH`: edited or cropped descendant |
| `likely_match` | `--scan` found a record within `T_NEAR` (watermark not decoded) |
| `disputed` | the named record has an earlier look-alike (within `T_DUP`, 10) by a different signer |
| `not_found` | no record named, or nothing within threshold |
| `unsupported_version` | the requested fingerprint algorithm is not the supported one |
| `error` | the image, the RPC or the registry could not be read |

## Exit codes

- `0` for `verified` / `likely_match`
- `1` for `altered` / `disputed` / `not_found` / `unsupported_version`
- `2` for `error`

so it composes in shell scripts and CI.

## Why it matters

The web app applies thresholds on the server. This tool exists so a skeptical
user can reproduce the judgement — fingerprint, distances and the earlier-look-alike
check — from first principles, with the chain as the only shared state.
