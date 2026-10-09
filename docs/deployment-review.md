# Deployment review kit: closing the `disputeDuplicate` gap

**Status: prepared, NOT deployed.** This kit exists so a reviewer can sign off on
a fresh testnet deployment of the current source before any key broadcasts. No
transaction has been sent; the existing live registry
(`0xf4a792ddb0c83Bdf1Ed2E1220B197760d821396c`) is untouched.

## 1. The gap, made objective

`deploy/verify_deployment.py` derives every function selector from the source ABI
(`service/abi.json`) and checks it against the deployed runtime bytecode:

```
DRIFT: 5 source function(s) absent from the deployed contract:
  - DISPUTE_MAX_DISTANCE()
  - disputeDuplicate(bytes32,bytes32)
  - disputeOf(bytes32)
  - hammingDistance(bytes32,bytes32)
  - isDisputed(bytes32)
```

The live contract is the source as of `7e2ec49`. Everything except the
`disputeDuplicate` work is verified present (including the `recordsPage` clamp
was already released via a *different* mechanism — it is present because it was
in the deployed revision; the dispute feature and `recordOf`-adjacent new views
are not). The deploy simulation (`forge script`, no broadcast) completes against
Monad testnet: **2,755,242 gas, 0.559 MON** at the quoted fee.

## 2. Source and tests

- `contracts/src/ImprintRegistry.sol` — `DISPUTE_MAX_DISTANCE = 10`,
  `disputeDuplicate`, `hammingDistance`, `isDisputed`, `disputeOf`, `Dispute`
  struct, `RecordDisputed` event, `UnknownRecord`/`NotEarlier`/`AlreadyDisputed`/
  `NotSimilar` errors. `_popcount64` runs in `unchecked` (wrapping is intended).
- `forge test`: **28 passed** (21 original + 6 dispute tests + 1 gas-cost test in
  `SimilarityCost.t.sol`).
- `service/abi.json` was regenerated from the build to the full source ABI
  (29 entries) so the repository ABI no longer diverges from `src/`.

## 3. What changes on redeploy (the review surface)

| Item | Live today (`7e2ec49`) | New (current `src/`) |
|---|---|---|
| `recordsPage` clamp | present | present (same) |
| `disputeDuplicate(bytes32,bytes32)` | absent | new, permissionless, non-destructive |
| `hammingDistance(bytes32,bytes32)` | absent | new, pure, `bytes32`-level |
| `isDisputed` / `disputeOf` | absent | new views |
| `DISPUTE_MAX_DISTANCE` | absent | new constant (10) |
| `RecordDisputed` event | absent | new |
| errors | `AlreadyRegistered`, `BadSignature`… | + `UnknownRecord`, `NotEarlier`, `AlreadyDisputed`, `NotSimilar` |

Dispute semantics to review: each *later* ID can be disputed once; duplicating
must be strictly later (`e.blockNumber >= l.blockNumber` → `NotEarlier`); the
contract checks distance on-chain and never deletes or edits either record.

## 4. The review decision that gates everything: the data split

**A redeploy creates an empty registry.** The 114 records on `0xf4a792…` do not
move. After a redeploy there would be two live-imprint registries and a record
could be on either one. The reviewer must choose, and code must match the choice:

- **Option A — new epoch.** The new address is the registry; old records are
  read-only history served by the old address. Verification of a watermarked
  image must then know **which epoch** it belongs to (look up both addresses and
  take the one that exists), and the frontend/`chain.py`/`imprint_verify.py`
  must read a **list** of registry addresses, not a single one.
- **Option B — keep `0xf4a792…` as the single source of truth**, and ship
  `disputeDuplicate` as an additional small contract referenced by it, or do not
  redeploy the registry at all.

Recommendation: **Option A, implemented first** — make the registry address a
list everywhere (chain.py, imprint_verify.py, frontend config, `/config`) and
only then deploy, so no previously-registered image becomes unverifiable. This is
deliberately **not** implemented yet; it is the first item of the review.

## 5. Pre-deploy checklist (for the reviewer)

- [ ] `forge test` in `contracts/` — 28 pass.
- [ ] `python deploy/verify_deployment.py` against the **current** address shows
      the expected 5-function drift (proves the tool works).
- [ ] Decide Options A/B and confirm multi-registry reads if A (section 4).
- [ ] `python -m pytest -q` in `service/` — 90 pass (with the regenerated ABI).
- [ ] Review `contracts/src/ImprintRegistry.sol` diffs and
      `contracts/test/ImprintRegistry.t.sol` additions.
- [ ] Fund the deployer (`0x8BaeBeA2E0De504d878b227a36672B7d0Ff2015D` or the
      new key) — expected ~0.6 MON.

## 6. Deploy procedure (only after approval + a funded key)

```bash
cd contracts
export PRIVATE_KEY=<testnet-only key>        # never log this
forge script script/Deploy.s.sol \
  --rpc-url https://testnet-rpc.monad.xyz \
  --private-key "$PRIVATE_KEY" \
  --broadcast --slow
```

## 7. Post-deploy verification (all required before anything points at it)

- [ ] `python deploy/verify_deployment.py --address <new>` exits **IN SYNC**
      (every source function present).
- [ ] `cast call <new> "count()(uint256)"` → 0.
- [ ] `cast call <new> "DISPUTE_MAX_DISTANCE()(uint256)"` → 10, and a 2-register
      keep-or-distort pair passes/`NotSimilar` as the unit tests expect.
- [ ] Sourcify verify at the new address (`exact_match`).
- [ ] Update `deployments/monad-testnet.json` (new address, deployTx, block,
      `supersedes` the old one — the manifest pattern already records history).
- [ ] Update `service/chain.py` `REGISTRY` default, `service/imprint_verify.py`
      `DEFAULT_REGISTRY`, `web/src/lib/batch.json`, README, and `.env.example`
      to the new address(es).
- [ ] Re-run `e2e_testnet.py` (one live registration round-trip) against the new
      address.

## 8. Reviewer sign-off

| Reviewer | Role | Date | Decision |
|---|---|---|---|
| (to fill) | protocol | — | Approve / changes |
| (to fill) | deployment/ops | — | Approve / changes |

Until both boxes are filled and the key exists, the correct next action is
**nothing** — the current registry keeps working unchanged.