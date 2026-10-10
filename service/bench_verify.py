"""Measure end-to-end verification latency against the live registry, read-only.

This is the gate for the authenticated-index question: the index stays opt-in
until a *measured* verify (fetch all records + compare the published fingerprint
recipe) exceeds the latency budget at the registry size we actually care about.
BK-tree search was already measured slower than the linear scan at radius 10/16/24
(test_index.py), so this script measures the linear path that ships.

No writes, no gas, one wallet-free process. Uses the same modules as the API.
"""
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import chain  # noqa: E402
import fingerprint as fp  # noqa: E402


def timeit(fn, *a):
    t0 = time.perf_counter()
    r = fn(*a)
    return time.perf_counter() - t0, r


def main() -> int:
    t, n = timeit(lambda: chain.count(fresh=True))
    print(f"registry size (live count()): {n}")
    t_scan, recs = timeit(chain.all_records)
    assert len(recs) >= 1, f"unexpectedly empty registry: {len(recs)}"
    print(f"fetch all records: {t_scan:.2f}s for {len(recs)} records "
          f"({t_scan / len(recs) * 1e3:.1f} ms/record), game over the RPC")

    # the actual compare work for a full scan (pure CPU, no RPC)
    needle = random.getrandbits(256)
    keys = [fp.from_hex(r.fingerprint) for r in recs]
    t_cmp, _ = timeit(lambda: [(k ^ needle).bit_count() for k in keys])
    print(f"fingerprint compare over {len(keys)} records: {t_cmp * 1e3:.2f} ms "
          f"({t_cmp / len(keys) * 1e6:.1f} us/record)")

    def project(size):
        pages = (size + 99) // 100
        fetch = t_scan / ((len(recs) + 99) // 100) * pages  # one eth_call per 100 records
        cmp = t_cmp / len(keys) * size
        rpc = fetch  # recordById fallback roughly one call -> dominated by the scan anyway
        return {"records": size, "fetch_ms": round(fetch * 1e3), "compare_us": round(cmp * 1e6),
                "total_ms": round((fetch + cmp) * 1e3), "rpc_calls_for_scan": pages}

    sizes = [n, 1000, 10_000, 100_000, 1_000_000]
    table = [project(s) for s in sizes]
    for row in table:
        print(f"  {row['records']:>9,} records -> fetch {row['fetch_ms']:>7,} ms "
              f"+ compare {row['compare_us']:>9,} us = {row['total_ms']:>8,} ms full scan "
              f"(worst-case, no index)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())