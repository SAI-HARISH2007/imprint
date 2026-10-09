"""Reproducible lookup benchmark: BK-tree vs linear scan over 256-bit fingerprints.

The service guards registration (radius T_DUP = 10) and the unmarked-verify
fallback (radius T_NEAR = 24) by scanning stored fingerprints. This measures the
cost of that scan as the registry grows, and checks whether the opt-in BK-tree
(service/index.py) actually helps.

Fingerprints are drawn uniform-random, which is the *worst* case for BK-tree
pruning: real near-duplicates cluster and prune better, but they also mean the
registry is not adversarial. Random is the honest neutral baseline.

Run:  python bench_lookup.py
      python bench_lookup.py --sizes 10000,100000,1000000 --queries 100 --json
"""
import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import index  # noqa: E402

RADII = (10, 16, 24)


def _linear(keys, k, r):
    return sum(1 for x in keys if (x ^ k).bit_count() <= r)


def bench(n, q, seed):
    rng = random.Random(seed)
    keys = [rng.getrandbits(256) for _ in range(n)]
    t = time.perf_counter()
    tree = index.build((k, i) for i, k in enumerate(keys))
    build_s = time.perf_counter() - t
    queries = [rng.getrandbits(256) for _ in range(q)]

    row = {"n": n, "queries": q, "build_s": round(build_s, 3)}
    for r in RADII:
        t = time.perf_counter()
        for k in queries:
            tree.search(k, r)
        row[f"bk_r{r}_ms"] = round(1000 * (time.perf_counter() - t) / q, 3)
        t = time.perf_counter()
        for k in queries:
            _linear(keys, k, r)
        row[f"linear_r{r}_ms"] = round(1000 * (time.perf_counter() - t) / q, 3)
        row[f"bk_over_linear_r{r}"] = round(row[f"bk_r{r}_ms"] / row[f"linear_r{r}_ms"], 2)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="10000,100000,1000000")
    ap.add_argument("--queries", type=int, default=0, help="default scales down as n rises")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = []
    for n in (int(s) for s in args.sizes.split(",")):
        q = args.queries or max(20, min(200, 2_000_000 // n))
        row = bench(n, q, args.seed)
        rows.append(row)
        print(
            f"n={row['n']:>9}  build {row['build_s']:>5}s  "
            + "  ".join(
                f"r{r}: linear {row[f'linear_r{r}_ms']:>7}ms  bk {row[f'bk_r{r}_ms']:>7}ms ({row[f'bk_over_linear_r{r}']}x)"
                for r in RADII
            ),
            flush=True,
        )

    print(
        "\nRead: 'x' > 1 means the BK-tree is slower than the linear scan. "
        "Median linear time at 1M records is the CPU floor; the real verifier cost "
        "is fetching records over RPC (see docs/scaling.md)."
    )
    if args.json:
        print(json.dumps({"radii": list(RADII), "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
