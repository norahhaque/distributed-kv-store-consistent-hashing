"""Consistent hash ring: decides which KV store owns each key.
Authors: Norah, Aymah

Picture a clock face with positions 0 .. 2**32 - 1 (the "ring").
  - Every store is placed on the ring many times ("virtual nodes"), at the
    positions hash("<store>#0"), hash("<store>#1"), ...
  - A key is hashed to a position too. Its owner is the first store position
    found by walking clockwise from there (wrapping around at the end).

When a store is added or removed, only the keys next to its positions change
owner (about 1/N of all keys). Every other key stays where it was.

Example:
  ring = HashRing(["http://localhost:8081", "http://localhost:8082"])
  ring.get_node("user:42")              # -> "http://localhost:8082"
  ring.add_node("http://localhost:8083")
  ring.remove_node("http://localhost:8081")
"""
import bisect
import hashlib


def hash_value(text):
    """Turn any string into a whole number between 0 and 2**32 - 1 (a spot on the ring).

    We use MD5 instead of Python's built-in hash(), because hash() gives a
    different answer every time Python starts. Two programs (or one program run
    twice) would then disagree about where a key lives. MD5 always gives the same
    answer for the same text. (We only need an even spread, not security.)
    """
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()  # 32 hex characters, e.g. "5d41402a..."
    return int(digest[:8], 16)  # first 8 hex characters = a 32-bit number


class HashRing:
    def __init__(self, nodes=(), vnodes=500):
        self.vnodes = vnodes  # spots per store; 500 chosen from analyze_hashing.py (keeps stores within ~10% of each other)
        self._positions = []  # every spot on the ring, kept sorted from small to large
        self._owner = {}  # spot on the ring -> the store that owns that spot
        for node in nodes:
            self.add_node(node)

    def add_node(self, node):
        """Put a store on the ring at `vnodes` different spots."""
        for i in range(self.vnodes):
            pos = hash_value(f"{node}#{i}")
            if pos in self._owner:  # two spots landed on the same number (almost never happens): skip it
                continue
            self._owner[pos] = node
            bisect.insort(self._positions, pos)  # insert while keeping the list sorted

    def remove_node(self, node):
        """Take all of a store's spots off the ring."""
        self._positions = [p for p in self._positions if self._owner[p] != node]
        self._owner = {p: n for p, n in self._owner.items() if n != node}

    def get_node(self, key):
        """Return the store that owns `key`: the first spot clockwise from hash(key)."""
        if not self._positions:
            raise ValueError("hash ring is empty: add at least one node first")
        pos = hash_value(key)
        # Binary search: index of the first spot that is larger than pos
        i = bisect.bisect_right(self._positions, pos)
        if i == len(self._positions):  # walked past the last spot, so wrap around to the first one
            i = 0
        return self._owner[self._positions[i]]

    @property
    def nodes(self):
        """The stores currently on the ring (sorted, no duplicates)."""
        return sorted(set(self._owner.values()))
