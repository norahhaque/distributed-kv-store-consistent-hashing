"""Move keys to their new owner when a store is added or removed, then demo it live.
Authors: Norah, Aymah

When the list of stores changes, the hash ring changes, so some keys now belong to
a different store than the one holding them. rebalance() finds those keys and moves
them. Thanks to consistent hashing only about 1/N of the keys need to move.

Demo (needs Docker running; starts and stops the containers itself):
  python rebalance.py
"""
import subprocess
import sys
import time

from kv_client import ShardedKVClient, wait_until_ready

KV1, KV2, KV3 = "http://localhost:8081", "http://localhost:8082", "http://localhost:8083"
NUM_KEYS = 3000


def rebalance(old_nodes, new_nodes):
    """Move every key that the new ring assigns to a different store.

    old_nodes: every store that currently holds data (including one about to be removed).
    new_nodes: the stores that should hold data from now on.
    Returns how many keys were moved.
    """
    client = ShardedKVClient(new_nodes)  # its ring is the NEW layout
    moved = 0
    for node in old_nodes:
        for key in client.keys_on(node):  # every key this store holds right now
            new_owner = client.node_for(key)
            if new_owner == node:
                continue  # still in the right place, which is true for most keys
            value = client.get_from(node, key)
            if value is None:
                continue  # deleted in the meantime, nothing to move
            client.put_to(new_owner, key, value)  # 1. copy to the new owner first...
            client.delete_from(node, key)  # 2. ...then remove from the old one
            moved += 1
    return moved


# ---------------------------------------------------------------- demo helpers

def compose(*args):
    """Run a docker compose command, e.g. compose("up", "-d", "kv3")."""
    subprocess.run(["docker", "compose", *args], check=True, capture_output=True)


def count_readable(nodes, keys):
    """How many keys can be read back with the right value through a client for these stores."""
    client = ShardedKVClient(nodes)
    return sum(client.get(k) == f"value_of_{k}" for k in keys)


def show_split(nodes):
    client = ShardedKVClient(nodes)
    for node in nodes:
        print(f"    {node} holds {len(client.keys_on(node))} keys")


def main():
    keys = [f"key_{i}" for i in range(NUM_KEYS)]
    ok = True

    print("Step 1: start kv1 + kv2 and write", NUM_KEYS, "keys")
    compose("down", "-v")  # clean slate
    compose("up", "-d", "--build", "kv1", "kv2")
    wait_until_ready([KV1, KV2])
    client = ShardedKVClient([KV1, KV2])
    for k in keys:
        client.put(k, f"value_of_{k}")
    show_split([KV1, KV2])

    print("\nStep 2: add kv3")
    compose("up", "-d", "kv3")
    wait_until_ready([KV3])
    # Without moving data, a 3-store client looks for some keys on kv3, which is still empty
    before = count_readable([KV1, KV2, KV3], keys)
    print(f"  before rebalancing: {before}/{NUM_KEYS} keys readable (the rest belong to kv3 now)")
    t0 = time.perf_counter()
    moved = rebalance([KV1, KV2], [KV1, KV2, KV3])
    print(f"  rebalanced: moved {moved} keys ({100 * moved / NUM_KEYS:.1f}%) "
          f"in {time.perf_counter() - t0:.2f}s")
    after = count_readable([KV1, KV2, KV3], keys)
    print(f"  after rebalancing:  {after}/{NUM_KEYS} keys readable")
    show_split([KV1, KV2, KV3])
    ok &= after == NUM_KEYS

    print("\nStep 3: remove kv2")
    t0 = time.perf_counter()
    moved = rebalance([KV1, KV2, KV3], [KV1, KV3])  # move kv2's keys away while it is still running...
    compose("stop", "kv2")  # ...then shut it down
    print(f"  rebalanced: moved {moved} keys ({100 * moved / NUM_KEYS:.1f}%) "
          f"in {time.perf_counter() - t0:.2f}s, then stopped kv2")
    after = count_readable([KV1, KV3], keys)
    print(f"  after removing kv2: {after}/{NUM_KEYS} keys readable")
    show_split([KV1, KV3])
    ok &= after == NUM_KEYS

    compose("down", "-v")
    print("\nPASS: no keys lost" if ok else "\nFAIL: some keys were lost")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
