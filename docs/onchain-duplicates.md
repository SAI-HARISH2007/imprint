# Can duplicate detection be enforced on chain? An evaluation

The service's near-duplicate refusal is policy, not consensus: a caller who signs
directly and calls `registerSigned`/`registerPasskey` can register a look-alike
(the bypass is documented in `docs/enforcement.md`). This note evaluates whether
that can be fixed *at the protocol level*, with measured cost, before choosing an
implementation. It does not change the contract.

## The measured cost of checking similarity on chain

A mandatory check has to compare the incoming fingerprint against stored ones,
because the contract has no way to know which stored record might be close — a
Hamming radius query is not an equality lookup and cannot be a mapping read. A
fairness caveat follows the numbers.

`contracts/test/SimilarityCost.t.sol` stores fingerprints in a storage array (as
the registry does) and scans within 10 bits with the same SWAR popcount the
registry uses. Result: **~3,418 gas per stored record scanned**, perfectly linear.

| stored records | scan gas (radius 10) | vs a registration (~173k gas) |
|---|---|---|
| 100 | 344,604 | ~2.0x |
| 1,000 | 3,420,804 | ~19.7x |
| 10,000 | 34,182,804 | ~197x |

A full scan is `O(n)` and unbounded, so it cannot be mandatory: it grows without
limit with the registry, and it is a denial-of-service lever — an attacker can
inflate the registry until registration hits the block gas limit and *nobody* can
register. Any on-chain check must therefore be **bounded**, not global.

## Options

| Option | Guarantee | Cost | Admin / trust | Notes |
|---|---|---|---|---|
| **1. Mandatory global scan at registration** | strong | `O(n)` gas, unbounded (34M @ 10k) | none | rejected: unbounded + DoS lever (above) |
| **2. Bounded recent-window scan** (last *K* records) | only recent squats | `K` x 3,418 gas; K=100 → 344k (~2x register) | none | constant cost; misses older duplicates; window size is a policy knob baked on chain |
| **3. Optimistic: allow + permissionless dispute** (built, source) | visibility, not prevention | registration `O(1)`; dispute = one `O(1)` `hammingDistance` | none | non-destructive; spam-resistant (one dispute per later id); **this is the current design** |
| **4. Bonded challenge / reversible registration** | strong, economic | `O(1)` + bond + window | needs slashing logic (no *admin*, but economics) | a griefer can dispute any near-dup; needs a bond to price that, which adds token/economic machinery |
| **5. ZK / committee attestation of an off-chain index** | as strong as the prover | off-chain + verify | new trust (prover/committee) unless full ZK | large effort; the integrity is only as good as the prover |

## Why the current design is the honest default

Option 3 is what ships: registration is `O(1)` and permissionless, and anyone can
irreversibly flag a near-duplicate with `disputeDuplicate` (source; pending
redeploy). The chain then holds an objective, checkable fact — "these two records
are within 10 bits" — with no owner and no way to delete either record. The
verifier turns that fact into the *disputed* verdict. This is prevention traded
for uncensorability, made visible. See `docs/enforcement.md`.

Making detection *enforced* rather than *visible* requires either:

- **Option 2** — a bounded recent-window check. It is affordable (~2x gas at
  K=100) and could be added as an opt-in second registration path that scans the
  last K records before `_store`. Honest limit: it only protects the recent tail,
  and the window is now a hardcoded policy. It also makes every registration pay,
  even from honest users.
- **Option 4** — a bonded challenge that can *revert* a registration. Stronger,
  but it prices disputes and reintroduces economic machinery the project
  deliberately avoids.

## Recommendation

1. **Do not** add a mandatory global scan (options measured too expensive and
   unbounded).
2. **Keep** option 3 (permissionless dispute) as the on-chain primitive; it is
   the right shape for an admin-free registry.
3. If a stronger guarantee is later required, add **option 2 as a separate,
   opt-in "strict" registration path** (scan the last K records, documented as a
   bounded guarantee), leaving the permissionless path intact. This is additive
   and does not weaken any existing property.
4. Any of these must be justified by a fresh measurement (gas and guarantee) and
   a redeploy — it is source-only work today.
