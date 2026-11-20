"""End-to-end check of the sharded store against the running containers.
Authors: Norah, Aymah

  docker compose up -d --build        # start the stores first
  python check_cluster.py 3           # check with 3 stores (or 1 or 2)

Steps:
  1. Write NUM_KEYS keys through the client.
  2. Read every key back and check its value.
  3. Ask each store for its key list and check that every key is on exactly one
     store, and on the store the hash ring says it should be on.
  4. Delete every key and check that the stores are empty again.
"""
import sys

from kv_client import ShardedKVClient, wait_until_ready

NUM_KEYS = 3000


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    nodes = [f"http://localhost:{8081 + i}" for i in range(n)]
    wait_until_ready(nodes)
    client = ShardedKVClient(nodes)
    keys = [f"key_{i}" for i in range(NUM_KEYS)]

    # 1. Write
    for k in keys:
        client.put(k, f"value_of_{k}")

    # 2. Read back
    wrong = [k for k in keys if client.get(k) != f"value_of_{k}"]
    print(f"read back: {NUM_KEYS - len(wrong)}/{NUM_KEYS} correct")

    # 3. Where did the keys end up?
    on_store = {node: set(client.keys_on(node)) for node in nodes}
    for node in nodes:
        print(f"  {node} holds {len(on_store[node])} keys ({100 * len(on_store[node]) / NUM_KEYS:.1f}%)")
    duplicates = sum(len(s) for s in on_store.values()) - len(set().union(*on_store.values()))
    misplaced = [k for k in keys if k not in on_store[client.node_for(k)]]
    print(f"keys stored on more than one store: {duplicates}")
    print(f"keys not on the store the ring picked: {len(misplaced)}")

    # 4. Clean up
    for k in keys:
        client.delete(k)
    left = sum(len(client.keys_on(node)) for node in nodes)
    print(f"keys left after deleting all: {left}")

    ok = not wrong and duplicates == 0 and not misplaced and left == 0
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
