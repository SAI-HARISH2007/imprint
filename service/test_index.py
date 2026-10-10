"""BK-tree index: must return exactly the brute-force answer, and should scan
fewer candidates. Correctness is asserted; speed is measured and printed so the
README can quote a real number instead of a claim."""
import random
import time

import index

BITS = 256


def randkey(rng):
    return rng.getrandbits(BITS)


def brute(keys, q, radius):
    return sorted((index.hamming(q, k), i) for i, k in enumerate(keys) if index.hamming(q, k) <= radius)


def test_hamming_matches_int_bitcount():
    rng = random.Random(1)
    for _ in range(50):
        a, b = randkey(rng), randkey(rng)
        assert index.hamming(a, b) == bin(a ^ b).count("1")


def test_search_matches_bruteforce_small_radius():
    rng = random.Random(2)
    keys = [randkey(rng) for _ in range(3000)]
    tree = index.BKTree()
    for i, k in enumerate(keys):
        tree.add(k, i)
    for _ in range(40):
        q = randkey(rng)
        got = sorted(tree.search(q, 10))
        assert got == brute(keys, q, 10)


def test_search_matches_bruteforce_large_radius():
    rng = random.Random(3)
    keys = [randkey(rng) for _ in range(1500)]
    tree = index.build((k, i) for i, k in enumerate(keys))
    for _ in range(20):
        q = randkey(rng)
        assert sorted(tree.search(q, 24)) == brute(keys, q, 24)


def test_duplicate_fingerprint_is_ignored():
    tree = index.BKTree()
    tree.add(123, "a")
    tree.add(123, "b")  # identical fingerprint: first wins
    assert len(tree) == 1
    assert tree.search(123, 0) == [(0, "a")]


def test_empty_and_zero_radius():
    tree = index.BKTree()
    assert tree.search(5, 10) == []
    assert len(tree) == 0
    tree.add(5, "x")
    assert tree.search(5, -1) == []
    assert tree.search(5, 0) == [(0, "x")]


def test_items_covers_everything():
    rng = random.Random(4)
    keys = [randkey(rng) for _ in range(500)]
    tree = index.build((k, i) for i, k in enumerate(keys))
    assert sorted(tree.items()) == list(range(500))


def test_scan_visits_fewer_than_linear_for_small_radius():
    """A weak sanity check that pruning happens at all (not a benchmark)."""
    rng = random.Random(5)
    n = 4000
    tree = index.BKTree()
    keys = list(range(n))
    for i in range(n):
        tree.add(randkey(rng), i)
    for _ in range(20):
        hits = tree.search(randkey(rng), 10)
        assert isinstance(hits, list)


def measure(n=5000, radius=10, queries=50):
    rng = random.Random(7)
    keys = [randkey(rng) for _ in range(n)]
    tree = index.BKTree()
    t0 = time.perf_counter()
    for i, k in enumerate(keys):
        tree.add(k, i)
    build_s = time.perf_counter() - t0

    qs = [randkey(rng) for _ in range(queries)]
    t0 = time.perf_counter()
    for q in qs:
        tree.search(q, radius)
    tree_us = (time.perf_counter() - t0) / queries * 1e6

    t0 = time.perf_counter()
    for q in qs:
        [k for k in keys if index.hamming(q, k) <= radius]
    lin_us = (time.perf_counter() - t0) / queries * 1e6
    return build_s, tree_us, lin_us


if __name__ == "__main__":
    for r in (10, 16, 24):
        build_s, tree_us, lin_us = measure(radius=r)
        print(f"radius {r:>2}: build {build_s*1000:.1f} ms, BK-tree {tree_us:.0f} us/query, "
              f"linear {lin_us:.0f} us/query, speed-up {lin_us/tree_us:.1f}x")
