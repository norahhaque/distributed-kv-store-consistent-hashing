"""Offline experiment on the hash ring (no servers or Docker needed).
Authors: Norah, Aymah

Answers two questions for the report:
  1. Balance: how evenly are keys spread across 3 stores for different numbers
     of virtual nodes?
  2. Movement: when a store is added, what fraction of keys must move to a new
     store? Modulo hashing (hash % N) vs. consistent hashing.

Run: python analyze_hashing.py     (prints tables, saves results/hashing_analysis.md)
"""
import os

from hash_ring import HashRing, hash_value

NUM_KEYS = 100_000
KEYS = [f"key_{i}" for i in range(NUM_KEYS)]
NODES = [f"http://localhost:{8081 + i}" for i in range(4)]  # 4 possible stores


def balance_table():
    lines = ["| Virtual nodes | Store 1 | Store 2 | Store 3 | Busiest / quietest |",
             "| ------------- | ------- | ------- | ------- | ------------------ |"]
    for vnodes in (1, 10, 100, 500):
        ring = HashRing(NODES[:3], vnodes=vnodes)
        counts = {n: 0 for n in NODES[:3]}
        for k in KEYS:
            counts[ring.get_node(k)] += 1
        shares = [100 * c / NUM_KEYS for c in counts.values()]
        ratio = max(shares) / min(shares)  # 1.00 would be a perfect split
        cells = " | ".join(f"{s:.1f}%" for s in shares)
        lines.append(f"| {vnodes} | {cells} | {ratio:.2f}x |")
    return lines


def modulo_owner(key, n):
    """The naive approach: store number = hash(key) % number_of_stores."""
    return hash_value(key) % n


def movement_table():
    lines = ["| Change | Ideal (1/new N) | Modulo hashing | Consistent hashing |",
             "| ------ | --------------- | -------------- | ------------------ |"]
    for old_n, new_n in ((1, 2), (2, 3), (3, 4)):
        mod_moved = sum(modulo_owner(k, old_n) != modulo_owner(k, new_n) for k in KEYS)
        old_ring = HashRing(NODES[:old_n])
        new_ring = HashRing(NODES[:new_n])
        ch_moved = sum(old_ring.get_node(k) != new_ring.get_node(k) for k in KEYS)
        lines.append(f"| {old_n} -> {new_n} stores | {100 / new_n:.1f}% | "
                     f"{100 * mod_moved / NUM_KEYS:.1f}% | {100 * ch_moved / NUM_KEYS:.1f}% |")
    return lines


if __name__ == "__main__":
    out = [f"## Key balance across 3 stores ({NUM_KEYS:,} keys)", "", *balance_table(), "",
           f"## Keys that must move when a store is added ({NUM_KEYS:,} keys)", "", *movement_table()]
    text = "\n".join(out) + "\n"
    print(text)
    os.makedirs("results", exist_ok=True)
    with open("results/hashing_analysis.md", "w") as f:
        f.write(text)
    print("saved results/hashing_analysis.md")
