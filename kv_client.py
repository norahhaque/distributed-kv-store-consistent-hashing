"""Sharded KV client: sends each key to the one store that owns it.
Authors: Norah, Aymah

The stores don't know about each other. Only this client knows the full list of
stores, and it uses the consistent hash ring to pick the right one for each key
("client-side routing").

Example:
  client = ShardedKVClient(["http://localhost:8081", "http://localhost:8082", "http://localhost:8083"])
  client.put("name", "alice")   # ring picks e.g. 8082 -> POST http://localhost:8082/name
  client.get("name")            # -> "alice"      (None if the key doesn't exist)
  client.delete("name")         # -> True         (False if the key didn't exist)
  client.node_for("name")       # -> "http://localhost:8082"
"""
import threading
import time
from urllib.parse import quote

import requests

from hash_ring import HashRing


class StoreUnavailable(Exception):
    """Raised when a store doesn't answer (container stopped, wrong port, timeout...)."""


class ShardedKVClient:
    def __init__(self, nodes, vnodes=500, timeout=5):
        self.ring = HashRing(nodes, vnodes)  # decides which store owns which key
        self.timeout = timeout  # seconds to wait for a store before giving up
        self._local = threading.local()  # holds one Session per thread (see _session)

    def _session(self):
        # A Session keeps connections open and reuses them, which is much faster than
        # opening a new connection for every request. Sessions must not be shared
        # between threads, so each thread gets its own the first time it asks.
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
        return self._local.session

    def _request(self, method, node, key="", **kwargs):
        # quote() makes any key safe to put in a URL, e.g. "a b?" -> "a%20b%3F".
        # The server turns it back into the original key automatically.
        url = f"{node}/{quote(key, safe='')}"
        try:
            return self._session().request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as e:
            # Say clearly which store failed instead of a long, confusing network error
            raise StoreUnavailable(f"store {node} did not respond: {e}") from e

    def node_for(self, key):
        """Which store owns this key."""
        return self.ring.get_node(key)

    # Normal use: the ring picks the store
    def put(self, key, value):
        self.put_to(self.node_for(key), key, value)

    def get(self, key):
        """Returns the value, or None if the key doesn't exist."""
        return self.get_from(self.node_for(key), key)

    def delete(self, key):
        """Returns True if the key existed and was deleted, False if it wasn't there."""
        return self.delete_from(self.node_for(key), key)

    # Direct use: the caller picks the store (rebalance.py needs this to move a key
    # from its old store to its new one)
    def put_to(self, node, key, value):
        r = self._request("POST", node, key, json={"value": value})
        r.raise_for_status()  # turn an error reply (400, 500, ...) into an exception

    def get_from(self, node, key):
        r = self._request("GET", node, key)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()["value"]

    def delete_from(self, node, key):
        r = self._request("DELETE", node, key)
        if r.status_code == 404:
            return False
        r.raise_for_status()
        return True

    def keys_on(self, node):
        """All keys stored on one specific store (uses the server's GET / endpoint)."""
        r = self._request("GET", node)
        r.raise_for_status()
        return r.json()["keys"]


def wait_until_ready(nodes, timeout=30):
    """Wait until every store answers GET / (containers need a moment to start up)."""
    deadline = time.time() + timeout
    for node in nodes:
        while True:
            try:
                if requests.get(f"{node}/", timeout=1).ok:
                    break  # this store is up, check the next one
            except requests.RequestException:
                pass  # not up yet
            if time.time() > deadline:
                raise StoreUnavailable(f"store {node} did not start within {timeout}s")
            time.sleep(0.2)
