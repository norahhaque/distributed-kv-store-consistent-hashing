# Sharded Key-Value Store with Consistent Hashing (CSCI 5144, Assignment 2)

Three copies of our Assignment 1 KV store run in Docker containers. A client uses a consistent hash ring
(500 virtual nodes per store) to send each key to exactly one store. Stores can be added or removed, and only
the keys whose owner changed are moved. The design, results and analysis are in [REPORT.md](REPORT.md).

## Setup

Requires Docker Desktop and Python 3.9+.

```bash
/usr/bin/python3 -m venv .venv        # on macOS, the system Python avoids Homebrew pip issues
source .venv/bin/activate
pip install -r requirements.txt       # flask, requests
pip install -r requirements-dev.txt   # matplotlib, for plots only
```

## Run

```bash
docker compose up -d --build          # start kv1, kv2, kv3 on localhost:8081-8083
python check_cluster.py 3             # end-to-end check: write, read back, placement, delete
python rebalance.py                   # live demo: add a store, remove a store, no keys lost
docker compose down -v                # stop and delete data
```

Use the client from Python:

```python
from kv_client import ShardedKVClient
client = ShardedKVClient(["http://localhost:8081", "http://localhost:8082", "http://localhost:8083"])
client.put("name", "alice"); client.get("name"); client.delete("name")
client.node_for("name")               # which store owns this key
```

Each store has the same HTTP API as Assignment 1 (`GET`/`POST`/`PUT`/`DELETE /<key>`), plus `GET /`, which
lists the store's keys.

## Tests and benchmarks

```bash
python -m unittest -v                 # 13 unit tests (store + hash ring), no Docker needed
python analyze_hashing.py             # key balance and key movement tables, no Docker needed

docker compose up -d --build
docker compose run --rm bench python kv_bench.py --docker --nodes 3 --threads 24 --procs 2
./run_experiments.sh                  # every configuration and trial (~25 min) -> results/*.csv
python plot_results.py                # figures and summary tables -> results/
```

The benchmark runs inside Docker (the `bench` service) because on macOS, requests from the host pass through
Docker Desktop's port forwarding, which was the bottleneck. See `REPORT.md` §8.

## Files

| File | Role |
| --- | --- |
| `hash_ring.py` | Consistent hash ring |
| `kv_server.py` | One store (Assignment 1 + `GET /` + `--log-level`) |
| `kv_client.py` | Sharded client that routes keys through the ring |
| `rebalance.py` | Moves keys when stores change; live demo |
| `check_cluster.py` | End-to-end check against running stores |
| `kv_bench.py` | Benchmark (throughput, latency percentiles, CSV output) |
| `analyze_hashing.py` | Offline key-balance and key-movement experiment |
| `run_experiments.sh` | Runs all experiments |
| `plot_results.py` | Figures and `results/summary.md` |
| `Dockerfile`, `docker-compose.yml` | Container image; stores and benchmark containers |
| `test_kv.py`, `test_hash_ring.py` | Unit tests |
| `results/` | Raw CSVs, figures, summary tables, diagnostics |
