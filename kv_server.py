"""Single-server key-value store
Authors: Norah, Aymah

HTTP API:
  GET    /<key>                      -> 200 {"key": k, "value": v}   or 404 if missing
  POST   /<key>  body {"value": v}   -> 200 {"key": k, "value": v}   (PUT is accepted too)
  DELETE /<key>                      -> 200 {"key": k, "deleted": true} or 404 if missing
  GET    /                           -> 200 {"count": n, "keys": [...]}  (all keys on this store;
                                        also used as a health check if it answers, the store is up)

To Run:
  python kv_server.py                # listens on 127.0.0.1:8080
  python kv_server.py --port 9000 --data-dir ./data --log-file ./logs/kv_server.log
  python kv_server.py --log-level WARNING   # quiet mode for benchmarks (no per-request log lines)
"""
import argparse
import json
import logging
import os
import threading

from flask import Flask, jsonify, request

log = logging.getLogger("kv") # logger we use everywhere with log.info(...)


class KVStore:
    """Thread-safe in-memory python dict made durable with an append-only log (AOF).

    Every PUT/DEL is appended to the AOF as one JSON line and fsync'd to disk
    before it changes the in-memory dict (this is write-ahead logging). On startup
    the AOF is then replayed to rebuild the dict and then its compacted so that it only holds
    the latest value of each live key.

    One lock is responsible for guarding both the dict and the AOF so concurrent PUT/DEL
    calls on the same key are applied one at a time, in the same order on
    disk as in memory. With this setup, it is so that the last writer wins and nothing is half-applied
    """

    def __init__(self, data_dir):
        os.makedirs(data_dir, exist_ok=True) # make the data folder if it doesn't exist
        self._path = os.path.join(data_dir, "kv.aof") # file on disk where every change is saved
        self._data = {} # the dict that holds keys and values
        self._lock = threading.Lock() # only one thread can touch the dict/file at a time
        self._replay() # load saved data from disk back into the dict
        self._compact() # shrink the file down to just the current data
        self._aof = open(self._path, "a", encoding="utf-8") # "a" = append, new lines go at the end

    # Rebuild the dict by redoing every change in the file, in order
    def _replay(self):
        if not os.path.exists(self._path): # first time running, nothing saved yet
            return
        with open(self._path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                try:
                    rec = json.loads(line) # turn the line of text into a dict
                except json.JSONDecodeError:
                    # A crash mid-write might have left a torn last line and so we skip it
                    log.warning("skipping corrupt AOF line %d", lineno)
                    continue
                if rec["op"] == "put":
                    self._data[rec["key"]] = rec["value"]
                elif rec["op"] == "del":
                    self._data.pop(rec["key"], None) # remove the key, no error if it's missing
        log.info("recovered %d keys from %s", len(self._data), self._path)

    # Rewrite the file so it only has one "put" line per key that still exists
    def _compact(self):
        tmp = self._path + ".tmp" # write to a temp file first so we never lose the old one
        with open(tmp, "w", encoding="utf-8") as f:
            for k, v in self._data.items():
                f.write(json.dumps({"op": "put", "key": k, "value": v}) + "\n")
            f.flush()
            os.fsync(f.fileno()) # make sure it is actually on disk
        os.replace(tmp, self._path) # swap the temp file in (all at once)

    # Add one change to the end of the file This doesnt change the dict
    def _append(self, rec):
        self._aof.write(json.dumps(rec) + "\n")
        self._aof.flush() # push it out of python's buffer
        os.fsync(self._aof.fileno()) # force the OS to write it to disk now!

    def get(self, key):
        """Returns (found, value)."""
        with self._lock: # lock is released automatically at the end of the with block
            if key in self._data:
                return True, self._data[key]
            return False, None

    def put(self, key, value):
        with self._lock:
            self._append({"op": "put", "key": key, "value": value}) # save to disk first
            self._data[key] = value # then update the dict

    def delete(self, key):
        """Returns True if the key existed."""
        with self._lock:
            if key not in self._data:
                return False
            self._append({"op": "del", "key": key}) # save to disk first
            del self._data[key] # then update the dict
            return True

    def keys(self):
        """Returns a list of every key on this store (a copy, so it is safe to use after the lock is released)."""
        with self._lock:
            return list(self._data)

    def close(self):
        with self._lock: # wait for any write in progress to finish before closing
            self._aof.close()


def create_app(store):
    app = Flask(__name__)

    # Helper to build an error reply like {"error": "key not found", "key": "x"}
    def error(status, message, key=None):
        body = {"error": message}
        if key is not None:
            body["key"] = key
        return jsonify(body), status

    # GET / lists every key on this store. rebalance.py uses it to find keys that must move,
    # and scripts call it to check that the store is up. (<path:key> below never matches
    # the bare "/", because a key must be at least one character so the routes don't clash.)
    @app.route("/", methods=["GET"])
    def list_keys():
        keys = store.keys()
        return jsonify({"count": len(keys), "keys": keys})

    # <path:key> means everything after the "/" becomes the key, so like GET /key_5 -> key = "key_5"
    @app.route("/<path:key>", methods=["GET"])
    def get_key(key):
        found, value = store.get(key)
        if not found:
            log.info("GET key=%r -> 404 not found", key)
            return error(404, "key not found", key)
        log.info("GET key=%r -> 200", key)
        return jsonify({"key": key, "value": value})

    # The benchmark uses POST, however we also allow PUT since the assignment calls it PUT
    @app.route("/<path:key>", methods=["POST", "PUT"])
    def put_key(key):
        body = request.get_json(silent=True) # silent=True gives None instead of crashing on bad JSON
        if not isinstance(body, dict) or "value" not in body: # body must look like {"value": ...}
            log.info("PUT key=%r -> 400 bad request", key)
            return error(400, 'request body must be JSON like {"value": ...}', key)
        store.put(key, body["value"])
        log.info("PUT key=%r value=%r -> 200", key, body["value"])
        return jsonify({"key": key, "value": body["value"]})

    @app.route("/<path:key>", methods=["DELETE"])
    def delete_key(key):
        if not store.delete(key): # delete returns False if the key wasn't there
            log.info("DEL key=%r -> 404 not found", key)
            return error(404, "key not found", key)
        log.info("DEL key=%r -> 200", key)
        return jsonify({"key": key, "deleted": True})

    # Return JSON (not Flask's default HTML pages) for any other error.
    @app.errorhandler(404)
    def not_found(e):
        return error(404, "not found")

    @app.errorhandler(405) # e.g. someone sends PATCH, which we don't support
    def method_not_allowed(e):
        return error(405, "method not allowed")

    @app.errorhandler(500) # unexpected bug, log it instead of crashing
    def internal_error(e):
        log.exception("internal error")
        return error(500, "internal server error")

    return app


def setup_logging(log_file, level="INFO"):
    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True) # make the logs folder
    fmt = logging.Formatter("%(asctime)s [%(threadName)s] %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_file, encoding="utf-8") # write logs to the file
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler() # also print logs in the terminal
    console.setFormatter(fmt)
    # INFO = log every request. WARNING = only problems, so log.info(...) lines are skipped.
    # Benchmarks use WARNING so we measure the store itself, not the cost of writing log lines.
    log.setLevel(level)
    log.addHandler(file_handler)
    log.addHandler(console)
    # Hide Flask's own per-request access lines; our log already records each op.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def main():
    # command line options, defaults are used if you just run python kv_server.py
    parser = argparse.ArgumentParser(description="Single-server key-value store")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--log-file", default="logs/kv_server.log")
    parser.add_argument("--log-level", default="INFO", choices=["INFO", "WARNING"])
    args = parser.parse_args()

    setup_logging(args.log_file, args.log_level)
    store = KVStore(args.data_dir) # loads any saved data from disk
    app = create_app(store)
    log.info("listening on http://%s:%d", args.host, args.port)
    try:
        # threaded=True: each incoming request is handled on its own thread!
        app.run(host=args.host, port=args.port, threaded=True)
    finally:
        # runs when the server stops (for example Ctrl+C) so the file is closed cleanly
        store.close()
        log.info("server stopped")


if __name__ == "__main__":
    main()
