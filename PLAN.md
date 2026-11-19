# Assignment 2 Plan: Distributed KV Store with Consistent Hashing

**Team:** Norah, Aymah. **Due:** Thu 2026-11-20 (night). Phase 11 is cut unless we finish early.

We build on the Assignment 1 store (`../hw_1`). Plan: run **three copies** of it in Docker containers, split
the keys across them with **consistent hashing**, then measure how **throughput** and **latency** change as we go
from 1 to 2 to 3 stores.

## Progress

| #  | Phase                                         | Status      |
| -- | --------------------------------------------- | ----------- |
| 0  | Concepts primer (read before coding)          | done        |
| 1  | Project setup and baseline check              | done        |
| 2  | Consistent hashing ring (`hash_ring.py`)      | done        |
| 3  | Small server additions (`kv_server.py`)       | done        |
| 4  | Containers: Dockerfile + `docker-compose.yml` | done        |
| 5  | Sharded client (`kv_client.py`)               | not started |
| 6  | Adding/removing stores while running          | not started |
| 7  | Benchmark upgrade (`kv_bench.py`)             | not started |
| 8  | Run the experiments (1 → 2 → 3 stores)        | not started |
| 9  | Graphs and tables (`plot_results.py`)         | not started |
| 10 | Report + README, final submission             | not started |
| 11 | (Stretch) Replication for fault tolerance     | optional    |

Rule for every phase: **build a small piece → test it → write down any problem in the Challenges Log (bottom of
this file) → move on.** The Challenges Log becomes the "challenges faced" section of the report.

---

## Phase 0: Concepts primer

Short versions here. Each one gets a fuller explanation when we reach the phase that uses it.

**Sharding (partitioning).** One server holds every key, so all requests wait in its single line. With three
servers we split the keys so each server holds about one third of them and gets about one third of the requests.
Each piece is called a *shard*. The hard part is deciding which server owns a given key.

**Naive approach: `server = hash(key) % N`.** A *hash* turns any string into a big number that looks random but is
always the same for the same input. Taking it modulo N gives a server number from 0 to N-1. The problem shows up
when N changes, for example 3 → 4: almost every key's `% N` changes (about 75% of keys move), so nearly all the
data has to be shuffled between servers.

**Consistent hashing.** Picture a clock face (the *ring*) with positions 0 … 2³²−1. Hash each server's name to a
spot on the ring. To find a key's owner, hash the key to a spot and **walk clockwise until you reach a server**.
When a server is added, it only takes the keys between itself and the previous server on the ring. Only about 1/N
of keys move and the rest stay where they are. That is why the assignment says the system "remains operational
when the number of KV stores changes."

**Virtual nodes.** With only 3 points on the ring, the slices come out uneven (one server might get 60% of the
keys). The fix is to put each server on the ring many times (`kv1#0`, `kv1#1`, … `kv1#99`). Many small slices
average out to roughly even shares. We will measure this ourselves.

**Container (Docker).** A container is a lightweight, isolated box that runs one program along with everything
that program needs (Python, Flask). An *image* is the recipe/snapshot and a *container* is a running copy of it.
The *Dockerfile* is the instructions for building the image. Three containers from one image work like three
small separate machines, each with its own memory, disk, and process.

**Docker Compose.** A YAML file (`docker-compose.yml`) that describes several containers at once: "run kv1, kv2,
kv3 from this image, expose them on ports 8081/8082/8083, give each its own storage." Then
`docker compose up kv1 kv2` starts exactly the containers you name.

**Port mapping and volumes.** Inside every container the server listens on port 8080. Port mapping (`8081:8080`)
means "traffic to my laptop's port 8081 goes to that container's 8080." A *volume* is storage that lives outside
the container, so the append-only log (AOF) survives if the container is deleted and recreated.

**Throughput and latency.** *Throughput* is how many operations finish per second (ops/s, higher is better).
*Latency* is how long one operation takes (ms, lower is better). We report the average and *percentiles*: p50 =
the median request, p99 = the request slower than 99% of the others (the "unlucky user" experience).

**Why more stores should help.** Each store has a single lock and does an `fsync` (forces a disk write) on every
PUT, so one store handles writes one at a time. Three stores means three locks, three disks, and three Python
processes working in parallel.

---

## Architecture (what we are building)

```
                 your laptop (benchmark / client program)
   ┌───────────────────────────────────────────────────────────┐
   │ kv_bench.py ──uses──> kv_client.py ──uses──> hash_ring.py │
   │                       "which store owns key_42?" → kv2    │
   └───────┬──────────────────────┬──────────────────────┬─────┘
           │ HTTP :8081           │ HTTP :8082           │ HTTP :8083
   ┌───────▼───────┐      ┌───────▼───────┐      ┌───────▼───────┐
   │ container kv1 │      │ container kv2 │      │ container kv3 │   started by
   │ kv_server.py  │      │ kv_server.py  │      │ kv_server.py  │   docker-compose.yml
   │ volume kv1    │      │ volume kv2    │      │ volume kv3    │
   └───────────────┘      └───────────────┘      └───────────────┘
```

**Key design decision: the routing happens in the client, not in a middle "router" server.** The client knows the
list of stores, runs the hash ring itself, and sends each request directly to the store that owns the key. Why:

- Simpler: no extra server to write, containerize, and debug.
- Faster: a router adds a second network hop to every request, and a single Python router would become the new
  bottleneck, which would hide the scaling we want to show.
- Real systems use this pattern too (memcached clients, Redis Cluster "smart clients").

Analogy: a router is a central post office that every letter passes through. Client-side routing means the
sender already knows the address and mails it directly. Both use the same hash ring; the only difference is
*where* it runs. The assignment only requires consistent hashing to spread the load, not a router.

(The report's design section explains this trade-off. Building a router for comparison is an optional extra.)

**Second decision: we write our own ring (~40 lines) instead of using a library.** The assignment allows a
library, but our own code is short, you'll understand every line, and it counts toward "innovation."

---

## Final file layout (`hw_2/`)

| File                   | What it does                                                                   | New / changed |
| ---------------------- | ------------------------------------------------------------------------------ | ------------- |
| `kv_server.py`         | The KV store from Assignment 1, plus a key-listing endpoint and a quiet mode   | small changes |
| `hash_ring.py`         | Consistent hash ring: add/remove a store, find the store for a key             | new           |
| `kv_client.py`         | `ShardedKVClient`: get/put/delete that sends each key to the right store       | new           |
| `rebalance.py`         | Moves keys to their new owner when a store is added or removed                 | new           |
| `analyze_hashing.py`   | Offline experiment: key balance and keys moved (modulo vs. consistent)         | new           |
| `kv_bench.py`          | Benchmark: runs against 1–3 stores, records throughput/latency to CSV          | rewritten     |
| `run_experiments.sh`   | Starts 1, then 2, then 3 containers, runs the benchmark several times each     | new           |
| `plot_results.py`      | Turns the CSV results into PNG graphs and a markdown table                     | new           |
| `test_kv.py`           | Old unit tests for the single store (should still pass)                        | unchanged     |
| `test_hash_ring.py`    | Unit tests for the ring                                                        | new           |
| `Dockerfile`           | Image recipe (renamed from `Dockerfile.txt` so Docker finds it automatically)    | renamed       |
| `docker-compose.yml`   | Defines containers kv1, kv2, kv3                                               | new           |
| `results/`             | CSV results + PNG graphs                                                       | generated     |
| `README.md`            | How to run everything                                                          | updated       |
| `REPORT.md` (→ PDF)    | The report you submit                                                          | new           |

How the files connect: `kv_bench.py` → `kv_client.py` → `hash_ring.py`, and `kv_client.py` → HTTP →
`kv_server.py` running in containers. `rebalance.py` uses `kv_client.py`. `run_experiments.sh` drives Docker and
`kv_bench.py`. `plot_results.py` reads what the benchmark wrote.

---

## Phase 1: Project setup and baseline check

Goal: a fresh `hw_2` folder with working Assignment 1 code, so Assignment 1 stays untouched as submitted.

1. Copy `kv_server.py`, `kv_bench.py`, `test_kv.py`, `requirements.txt`, `.gitignore`, `.dockerignore` from
   `hw_1` into `hw_2`. Copy `Dockerfile.txt` and rename it to `Dockerfile`.
2. Create a virtual environment with the system Python (Homebrew's Python 3.15 breaks pip):
   `/usr/bin/python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
3. Run `python -m unittest -v`. All old tests should pass.
4. Start Docker Desktop. In Settings → Resources, give Docker **at least 6 CPUs and 4 GB RAM** (needed so 3
   stores + benchmark don't fight over one CPU; we write the exact numbers in the report).
5. `docker build -t kv-store .` and `docker run --rm -p 8080:8080 kv-store`, then `curl` a PUT/GET to confirm the
   single container works.
6. (You) `git init`, create a new GitHub repo, first commit.

✅ Checkpoint: tests pass, one container answers curl.

## Phase 2: Consistent hashing ring (`hash_ring.py`)

Goal: a small class that answers "which store owns this key?"

```
ring = HashRing(["http://localhost:8081", "http://localhost:8082"], vnodes=100)
ring.get_node("user:42")   # -> "http://localhost:8082"
ring.add_node("http://localhost:8083")
ring.remove_node("http://localhost:8081")
```

How it works: a sorted list of ring positions plus a dict `position → store`. `get_node` hashes the key and uses
binary search (`bisect`) to find the first position clockwise, wrapping to the start of the list at the end.

Important detail: we hash with **MD5 from `hashlib`, not Python's built-in `hash()`**. Python randomizes
`hash()` for strings every time a program starts, so two programs (or one program restarted) would disagree about
where keys live. MD5 always gives the same answer. (Security doesn't matter here, we only need an even spread.)

Then:

- `test_hash_ring.py`: same key → same store every time; keys spread across all stores; adding a store only moves
  keys *to* the new store; removing a store only moves *that store's* keys; an empty ring raises a clear error.
- `analyze_hashing.py` (no Docker needed, runs in seconds) produces two tables for the report:
  1. **Balance:** % of 100,000 keys per store for vnodes = 1, 10, 100, 500.
  2. **Keys moved when going 2 → 3 stores (and 3 → 4):** modulo hashing (about 67%/75%) vs. consistent hashing
     (about 33%/25%).

✅ Checkpoint: tests pass, and both tables look like the theory predicts.

## Phase 3: Small server additions (`kv_server.py`)

Most of the server stays the same; each container runs the same code as before. Three small additions:

1. `GET /` → lists the keys this store holds (`{"keys": [...], "count": n}`). Needed by `rebalance.py` to know what
   to move, and useful for showing how keys are spread across the stores.
2. ~~`GET /_health`~~ Dropped: `GET /` doubles as the health check (if it answers, the store is up). A
   `/_health` route would clash with `/<path:key>` (a key literally named `_health` would behave oddly).
3. `--log-level` flag. Logging every request to file + console is slow, so benchmark runs use `WARNING` and the
   benchmark measures the store instead of the logging. We'll measure the difference, which is a good report point.

Add unit tests for the new endpoints to `test_kv.py`.

✅ Checkpoint: all tests pass.

## Phase 4: Containers (`Dockerfile`, `docker-compose.yml`)

```yaml
services:
  kv1: { build: ., ports: ["8081:8080"], volumes: ["kv1-data:/app/data"], cpus: 1.0 }
  kv2: ...8082...
  kv3: ...8083...
volumes: { kv1-data: {}, kv2-data: {}, kv3-data: {} }
```

- One image, three containers. Each has **its own volume**, so its AOF survives restarts.
- **`cpus: 1.0` per container.** This makes each container behave like one separate 1-CPU machine. Without it,
  one container could use the whole laptop and the 1-vs-3 comparison wouldn't be fair. We'll explain this in the
  report as a deliberate experimental choice.
- Named volumes (not folder mounts), because folder mounts on macOS are slow and would distort fsync timings.
- Quiet logging (`--log-level WARNING`) set via `command:`. Readiness is checked by scripts polling `GET /`.

Commands you'll learn: `docker compose up -d kv1`, `docker compose up -d kv1 kv2 kv3`, `docker compose ps`,
`docker compose logs kv2`, `docker stats`, `docker compose down` (and `down -v` to wipe data).

✅ Checkpoint: all three containers are running; `curl localhost:8081/_health` (and 8082, 8083) answer.

## Phase 5: Sharded client (`kv_client.py`)

```
client = ShardedKVClient(["http://localhost:8081", "http://localhost:8082", "http://localhost:8083"])
client.put("name", "alice")      # ring says kv2 → POST http://localhost:8082/name
client.get("name")               # → GET  http://localhost:8082/name → "alice"
client.delete("name")
client.node_for("name")          # "http://localhost:8082" (handy for demos)
```

- Uses `hash_ring.py` to choose the store, then the same HTTP calls the old benchmark made.
- One `requests.Session` per thread (reuses connections, as in the old benchmark).
- Clear errors: a missing key returns `None`, an unreachable store raises an error that names which store failed.

Integration check (a small script/test run against the live containers): write 3,000 keys, read every one back,
then call `GET /` on each store to confirm (a) every key is on exactly one store and (b) the split is about
1/3 each.

✅ Checkpoint: 3,000/3,000 keys read back correctly, and each store holds roughly 1,000.

## Phase 6: Adding/removing stores while running (`rebalance.py`)

This is the "system remains operational when the number of KV stores changes" requirement.

- `rebalance(old_nodes, new_nodes)`: for every key on every store, ask the *new* ring who should own it. If the
  owner changed, PUT the key on the new owner, then DELETE it from the old owner. (We copy first and delete
  second, so the key exists somewhere at every moment.)
- Demo script, run live and recorded for the report:
  1. Start kv1 + kv2 and write 3,000 keys.
  2. Start kv3 and run the rebalance. Print "moved X keys (Y%)", which should be about 33%.
  3. Read all 3,000 keys through a 3-store client: every one is found.
  4. Remove kv2 (rebalance its keys away, then stop it). Read all 3,000 again: every one is found.
- Explain the limitation honestly: keys being moved during the rebalance can briefly be read from the old owner.
  Real systems handle that with extra care, and we discuss it in the report.

✅ Checkpoint: zero lost keys after both add and remove.

## Phase 7: Benchmark upgrade (`kv_bench.py`)

Keep the structure of the old benchmark (phases, worker threads, queue, per-op timing) and change:

- Uses `ShardedKVClient`, with `--nodes 1|2|3` choosing how many stores.
- Parameters as flags: `--keys 10000 --threads 24 --trial 1`.
- **Same client load for every node count** (same threads, same keys). Only the number of stores changes, which
  is what makes the comparison fair.
- Short warm-up first (not measured), so connection setup doesn't count against latency.
- Records per phase (SET, GET): throughput, avg/p50/p95/p99 latency, errors, plus how many keys each store got.
- Appends one row per run to `results/results.csv`.
- Concept to learn here: *closed-loop load*. Each thread sends a request, waits for the answer, then sends the next
  one. That leads to **Little's Law: throughput ≈ threads ÷ average latency**, which we use in the report to
  explain why throughput goes up exactly when latency goes down.

✅ Checkpoint: one manual run against each of 1, 2, 3 stores produces sensible rows with 0 errors.

## Phase 8: Run the experiments (`run_experiments.sh`)

For N in 1, 2, 3: `docker compose down -v` (clean slate) → `up -d` the first N stores → wait for health → run the
benchmark **3 trials** → record. Then a **concurrency sweep**: threads = 4, 8, 16, 32 for each N, to show where a
single store saturates and how extra stores raise that ceiling.

While it runs, watch `docker stats` in another terminal. If the benchmark program itself is at 100% CPU, the
*client* is the bottleneck and we'd be measuring the wrong thing. If that happens we'll move the benchmark to
multiple processes. (Either way, this is worth writing up.)

Note in the report: all "machines" share one laptop, so the scaling won't be perfectly 3×. That's an honest,
expected limitation and we'll discuss it.

✅ Checkpoint: `results.csv` has every configuration × 3 trials with 0 errors.

## Phase 9: Graphs and tables (`plot_results.py`)

Uses matplotlib (added to `requirements.txt`). Produces in `results/`:

1. Throughput (ops/s) vs. number of stores, SET and GET, mean ± std over trials (bar chart).
2. Latency vs. number of stores: p50 / p95 / p99 (grouped bars).
3. Throughput vs. client threads, one line per store count (from the sweep).
4. Keys per store (the balance), plus the vnode-balance and keys-moved tables from Phase 2.
5. A markdown summary table pasted directly into the report.

## Phase 10: Report and submission

`REPORT.md` → exported to PDF. Sections:

1. Introduction and goal
2. Background: sharding, modulo vs. consistent hashing, virtual nodes, containers (in plain words)
3. Design: architecture diagram, client-side routing decision, MD5 choice, CPU limits, rebalance
4. Implementation: what each file does and how they connect
5. Experimental setup: hardware, Docker resources, workload, trials, fairness choices
6. Results: graphs + tables (throughput, latency, sweep, balance, keys moved)
7. Analysis: why it scales, why not perfectly 3×, Little's Law, where the bottleneck moves
8. Challenges faced and how we solved them (from the Challenges Log)
9. Limitations and future work (replication, router, real separate machines)
10. How to run

Also update `README.md` (setup, run, test, benchmark). You do the final commit/push.

## Phase 11 (stretch, only if time allows): Replication

Write each key to the next **2** distinct stores on the ring (a replication factor of 2), and read from the first
one that responds. Then stop a container mid-benchmark and show that reads still succeed. This turns "more
fault-tolerant" from a claim into a demo. It is the strongest "innovation" item, but we do it last because it
makes the code more complex.

---

## Challenges Log

(Filled in as we go. Format: *problem → cause → fix*. This becomes Report §8.)

- **Uneven key spread.** With 100 virtual nodes per store, one store got 36.6% of keys and another 29.2%
  (1.26x imbalance). → Too few ring positions for the random spacing to average out. → Measured 1/10/100/500 in
  `analyze_hashing.py` and set the default to 500 (1.09x). The lookup cost barely changes (binary search).
- **Python's `hash()` is not stable across runs** (string hashing is randomized each time Python starts). → Two clients
  would disagree about key owners. → Used MD5 from `hashlib`, which is deterministic.
- **Health route clashing with key routes.** `/_health` also matches `/<path:key>`. → Used the bare `/` instead,
  which `<path:key>` can never match (keys are at least 1 character), for both key listing and health checks.
- **`Dockerfile.txt` not found by `docker build`.** → Docker looks for a file named exactly `Dockerfile`. → Renamed it.
