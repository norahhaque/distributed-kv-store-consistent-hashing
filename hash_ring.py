"""Consistent hash ring, deciding which KV store owns each key
Authors: Norah, Aymah
"""
import bisect
import hashlib


def hash_value(text):
    """Turn any string into a whole number between 0 and 2**32 - 1 (a spot on the ring)

    We use MD5 instead of Python's built-in hash because hash() gives a
    different answer every time Python starts which means for us that two programs (or one program run
    twice) would then disagree about where a key lives. MD5 always gives the same
    answer for the same text and here we relaly only need an even spread and security is not a concenrn
    """
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()  # 32 hex characters 
    return int(digest[:8], 16)  # first 8 hex characters is a 32-bit number


class HashRing:
    def __init__(self, nodes=(), vnodes=500):
        self.vnodes = vnodes  # spots per store; 500 chosen from analyze_hashing.py (keeps stores within aroudb 10% of each other)
        self._positions = []  # every spot on the ring, kept sorted from small to large
        self._owner = {}  # spot on the ring -> the store that owns that spot
        for node in nodes:
            self.add_node(node)

    def add_node(self, node):
        """Put a store on the ring at `vnodes` different spots."""
        for i in range(self.vnodes):
            pos = hash_value(f"{node}#{i}")
            if pos in self._owner:  # two spots landed on the same number, skip skip it
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
        if i == len(self._positions):  # walked past the last spot so we hav eot wrap around to the first one
            i = 0
        return self._owner[self._positions[i]]

    @property
    def nodes(self):
        """The stores currently on the ring sorted and no dups"""
        return sorted(set(self._owner.values()))
