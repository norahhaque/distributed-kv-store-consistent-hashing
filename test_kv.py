"""Unit tests for the key-value store. Run: python -m unittest -v"""
import shutil
import tempfile
import threading
import unittest

from kv_server import KVStore, create_app


class KVTestCase(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.store = KVStore(self.data_dir)
        self.client = create_app(self.store).test_client()

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.data_dir)

    def test_put_get_delete(self):
        r = self.client.post("/a", json={"value": "1"})
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/a")
        self.assertEqual(r.get_json()["value"], "1")
        r = self.client.delete("/a")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/a").status_code, 404)

    def test_overwrite(self):
        self.client.post("/a", json={"value": "old"})
        self.client.put("/a", json={"value": "new"})
        self.assertEqual(self.client.get("/a").get_json()["value"], "new")

    def test_errors(self):
        r = self.client.get("/missing")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "key not found")
        self.assertEqual(self.client.delete("/missing").status_code, 404)
        self.assertEqual(self.client.post("/a", data="not json").status_code, 400)
        self.assertEqual(self.client.post("/a", json={"wrong": 1}).status_code, 400)
        self.assertEqual(self.client.patch("/a").status_code, 405)

    def test_list_keys(self):
        # Empty store -> no keys
        self.assertEqual(self.client.get("/").get_json(), {"count": 0, "keys": []})
        self.client.post("/a", json={"value": "1"})
        self.client.post("/b", json={"value": "2"})
        self.client.delete("/a")
        body = self.client.get("/").get_json()
        self.assertEqual(body, {"count": 1, "keys": ["b"]})  # deleted keys are not listed

    def test_persistence_across_restart(self):
        self.client.post("/a", json={"value": "1"})
        self.client.post("/b", json={"value": "2"})
        self.client.delete("/b")
        self.store.close()
        self.store = KVStore(self.data_dir)   # simulate a server restart
        self.assertEqual(self.store.get("a"), (True, "1"))
        self.assertEqual(self.store.get("b"), (False, None))

    def test_concurrent_writes_same_key(self):
        def hammer(i):
            for j in range(50):
                if j % 3 == 0:
                    self.store.delete("hot")
                else:
                    self.store.put("hot", f"t{i}-{j}")

        threads = [threading.Thread(target=hammer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        in_memory = self.store.get("hot")
        self.store.close()
        self.store = KVStore(self.data_dir)
        self.assertEqual(self.store.get("hot"), in_memory)


if __name__ == "__main__":
    unittest.main()
