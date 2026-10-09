"""A BK-tree over 256-bit fingerprints for sublinear near-duplicate search.

The registry grows over time and the service scans it on every registration and
every unmarked verify. A linear scan is O(n) 256-bit comparisons; a BK-tree
exploits the triangle inequality of the Hamming metric to visit only the
branches that can contain a fingerprint within the search radius.

Honest limits: a BK-tree prunes best for small radii. The registration guard
uses radius 10 and the unmarked fallback uses radius 24 out of a 256-bit
diameter, so the speed-up is real but modest and shrinks as the radius grows.
``test_index.py`` measures it against a brute-force scan on the same data and
the README reports the measured numbers rather than a theoretical claim.

The tree is append-only: registry records never change or disappear, so there
is no delete path.
"""
from __future__ import annotations


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


class _Node:
    __slots__ = ("key", "item", "children")

    def __init__(self, key: int, item):
        self.key = key
        self.item = item
        self.children: dict[int, "_Node"] = {}


class BKTree:
    """Maps 256-bit fingerprints (as ints) to opaque items (e.g. watermark ids)."""

    def __init__(self):
        self._root: _Node | None = None
        self._n = 0

    def __len__(self) -> int:
        return self._n

    def add(self, key: int, item) -> None:
        if self._root is None:
            self._root = _Node(key, item)
            self._n = 1
            return
        node = self._root
        while True:
            d = hamming(key, node.key)
            if d == 0:
                return  # identical fingerprint already present; first one wins
            child = node.children.get(d)
            if child is None:
                node.children[d] = _Node(key, item)
                self._n += 1
                return
            node = child

    def search(self, key: int, radius: int) -> list[tuple[int, object]]:
        """Every (distance, item) with distance <= radius. Order is unspecified."""
        if self._root is None or radius < 0:
            return []
        out: list[tuple[int, object]] = []
        stack = [self._root]
        while stack:
            node = stack.pop()
            d = hamming(key, node.key)
            if d <= radius:
                out.append((d, node.item))
            lo, hi = d - radius, d + radius
            for dist, child in node.children.items():
                if lo <= dist <= hi:
                    stack.append(child)
        return out

    def items(self):
        stack = [self._root] if self._root is not None else []
        while stack:
            node = stack.pop()
            yield node.item
            stack.extend(node.children.values())


def build(pairs) -> BKTree:
    """Build a tree from an iterable of (fingerprint_int, item)."""
    tree = BKTree()
    for key, item in pairs:
        tree.add(key, item)
    return tree
