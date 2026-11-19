"""Unit tests for the consistent hash ring. Run: python -m unittest -v"""
import unittest

from hash_ring import HashRing

A, B, C = "http://localhost:8081", "http://localhost:8082", "http://localhost:8083"
KEYS = [f"key_{i}" for i in range(10000)]


def owners(ring):
    """Map every test key to the store that owns it."""
    return {k: ring.get_node(k) for k in KEYS}


class HashRingTest(unittest.TestCase):
    def test_same_answer_every_time(self):
        # Two separately built rings must agree, just like two client programs would
        self.assertEqual(owners(HashRing([A, B, C])), owners(HashRing([A, B, C])))

    def test_order_of_adding_does_not_matter(self):
        self.assertEqual(owners(HashRing([A, B, C])), owners(HashRing([C, A, B])))

    def test_single_node_owns_everything(self):
        ring = HashRing([A])
        self.assertEqual(set(owners(ring).values()), {A})

    def test_keys_spread_evenly(self):
        counts = {A: 0, B: 0, C: 0}
        for node in owners(HashRing([A, B, C])).values():
            counts[node] += 1
        for node, n in counts.items():
            # A perfect split is 33.3% each; allow 25%-42%
            self.assertTrue(0.25 < n / len(KEYS) < 0.42, f"{node} got {n} keys")

    def test_adding_node_only_moves_keys_to_new_node(self):
        ring = HashRing([A, B])
        before = owners(ring)
        ring.add_node(C)
        after = owners(ring)
        moved = [k for k in KEYS if before[k] != after[k]]
        for k in moved:
            self.assertEqual(after[k], C)  # a key may only move to the newcomer
        # Roughly 1/3 of the keys should move (not ~2/3 as with modulo hashing)
        self.assertTrue(0.25 < len(moved) / len(KEYS) < 0.42)

    def test_removing_node_only_moves_its_own_keys(self):
        ring = HashRing([A, B, C])
        before = owners(ring)
        ring.remove_node(B)
        after = owners(ring)
        for k in KEYS:
            if before[k] != B:
                self.assertEqual(before[k], after[k])  # keys of A and C stay put
            else:
                self.assertIn(after[k], (A, C))  # B's keys go to the survivors
        self.assertEqual(ring.nodes, [A, C])

    def test_empty_ring_raises(self):
        with self.assertRaises(ValueError):
            HashRing().get_node("x")


if __name__ == "__main__":
    unittest.main()
