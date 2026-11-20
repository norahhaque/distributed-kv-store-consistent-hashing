"""Benchmark for the sharded KV store: measures throughput and latency with 1, 2 or 3 stores.
Authors: Norah, Aymah

Each thread acts as one user: it takes the next key from a queue, sends the request,
waits for the reply, and records how long it took. Two phases run:
  SET: write every key
  GET: read every key back and check the value is correct

One Python process can only run Python code on about one CPU core at a time (the GIL),
so with --procs the users are split across several processes (and the keys with them).

Usage (start the stores first):
  # recommended: run inside Docker, next to the stores (see docker-compose.yml)
  docker compose run --rm bench python kv_bench.py --docker --nodes 3 --threads 24 --procs 2
  # or from the laptop (slower: goes through Docker Desktop's port forwarding)
  python kv_bench.py --nodes 3 --keys 10000 --threads 24

Prints a summary and appends one row per phase to results/results.csv (or --out FILE).
"""
import argparse
import csv
import multiprocessing
import os
import queue
import threading
import time
from datetime import datetime

from kv_client import ShardedKVClient, wait_until_ready

FIELDS = ["time", "where", "nodes", "threads", "procs", "keys", "trial", "phase", "ok", "errors",
          "seconds", "throughput", "avg_ms", "p50_ms", "p95_ms", "p99_ms", "client_cpu_pct",
          "keys_per_store"]


def value_for(key):
    """The value we write for each key, so the GET phase knows what to expect."""
    return f"value_of_{key}"


class PhaseStats:
    """Results shared by all threads of one process (guarded by a lock)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.latencies = []  # seconds, one entry per successful request
        self.errors = 0  # failed requests or wrong values


def worker(client, work, stats, start_line):
    # Warm-up (not timed): open this thread's connection to every store, so connection
    # setup isn't counted in the measured latencies. "__warmup__" doesn't exist -> 404.
    for node in client.ring.nodes:
        client.get_from(node, "__warmup__")
    start_line.wait()  # wait until every thread is ready, then all start together

    while True:
        try:
            op, key = work.get_nowait()  # take the next job
        except queue.Empty:
            return  # no work left, this thread is done
        t0 = time.perf_counter()
        try:
            if op == "set":
                client.put(key, value_for(key))
                ok = True
            else:
                ok = client.get(key) == value_for(key)  # wrong value counts as an error
        except Exception:
            ok = False  # store down, timeout, error reply...
        latency = time.perf_counter() - t0
        with stats.lock:
            if ok:
                stats.latencies.append(latency)
            else:
                stats.errors += 1


def run_part(nodes, op, keys, num_threads):
    """Runs inside ONE process: num_threads users work through `keys`.

    Returns plain data (so it can be sent back from a child process):
    (latencies, errors, start time, end time, CPU seconds used by this process)
    """
    client = ShardedKVClient(nodes)  # each process needs its own client and connections
    work = queue.Queue()
    for key in keys:
        work.put((op, key))

    stats = PhaseStats()
    start_line = threading.Barrier(num_threads + 1)  # all workers + this thread
    threads = [threading.Thread(target=worker, args=(client, work, stats, start_line))
               for _ in range(num_threads)]
    for t in threads:
        t.start()
    start_line.wait()  # released once every worker has warmed up

    start, cpu0 = time.time(), time.process_time()
    for t in threads:
        t.join()  # wait for every worker to finish
    end = time.time()
    return stats.latencies, stats.errors, start, end, time.process_time() - cpu0


def run_phase(nodes, op, keys, num_threads, procs):
    """Split the users and keys across `procs` processes, run them, and combine the results."""
    procs = min(procs, num_threads)  # can't have a process with zero users
    # e.g. 24 threads over 2 procs -> [12, 12]; 1 key list -> every procs-th key per process
    threads_each = [num_threads // procs + (i < num_threads % procs) for i in range(procs)]
    jobs = [(nodes, op, keys[i::procs], threads_each[i]) for i in range(procs)]

    if procs == 1:
        parts = [run_part(*jobs[0])]
    else:
        with multiprocessing.Pool(procs) as pool:
            parts = pool.starmap(run_part, jobs)  # runs run_part(*job) in each process

    latencies = sorted(lat for part in parts for lat in part[0])
    errors = sum(part[1] for part in parts)
    # The phase lasts from the first process starting to the last one finishing
    seconds = max(part[3] for part in parts) - min(part[2] for part in parts)
    # CPU used by the benchmark: 100% = one full core. Close to procs * 100% would mean the
    # benchmark itself is the bottleneck, not the stores.
    cpu_pct = 100 * sum(part[4] for part in parts) / seconds
    return latencies, errors, seconds, cpu_pct


def percentile(sorted_values, p):
    """Value below which p% of the (already sorted) values fall."""
    return sorted_values[int(p / 100 * (len(sorted_values) - 1))]


def keys_per_store(nodes):
    """How many keys each store holds, e.g. "3390/3570/3040"."""
    client = ShardedKVClient(nodes)
    return "/".join(str(len(client.keys_on(node))) for node in nodes)


def save_row(row, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    new_file = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()  # column names on the first line only
        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Benchmark the sharded KV store")
    parser.add_argument("--nodes", type=int, default=3, choices=[1, 2, 3], help="number of stores")
    parser.add_argument("--keys", type=int, default=10000, help="keys per phase")
    parser.add_argument("--threads", type=int, default=24, help="simultaneous users (total)")
    parser.add_argument("--procs", type=int, default=1, help="processes to spread the users over")
    parser.add_argument("--trial", type=int, default=1, help="trial number (for repeated runs)")
    parser.add_argument("--out", default="results/results.csv", help="CSV file to append results to")
    parser.add_argument("--docker", action="store_true",
                        help="running inside Docker: reach stores as kv1:8080 instead of localhost:8081")
    args = parser.parse_args()

    if args.docker:  # inside Docker's network each container is reachable by its service name
        nodes = [f"http://kv{i + 1}:8080" for i in range(args.nodes)]
    else:  # from the laptop, through the published ports
        nodes = [f"http://localhost:{8081 + i}" for i in range(args.nodes)]
    wait_until_ready(nodes)
    keys = [f"key_{i}" for i in range(args.keys)]

    print(f"{args.nodes} store(s), {args.keys} keys, {args.threads} threads in {args.procs} "
          f"process(es), trial {args.trial}, {'docker' if args.docker else 'laptop'}")
    for op in ("set", "get"):
        lat, errors, seconds, cpu_pct = run_phase(nodes, op, keys, args.threads, args.procs)
        ok = len(lat)
        ms = lambda s: round(1000 * s, 2)  # seconds -> milliseconds
        row = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "where": "docker" if args.docker else "laptop",
            "nodes": args.nodes, "threads": args.threads, "procs": args.procs, "keys": args.keys,
            "trial": args.trial, "phase": op.upper(), "ok": ok, "errors": errors,
            "seconds": round(seconds, 3), "throughput": round(ok / seconds, 1),
            "avg_ms": ms(sum(lat) / ok) if ok else "",
            "p50_ms": ms(percentile(lat, 50)) if ok else "",
            "p95_ms": ms(percentile(lat, 95)) if ok else "",
            "p99_ms": ms(percentile(lat, 99)) if ok else "",
            "client_cpu_pct": round(cpu_pct),
            "keys_per_store": keys_per_store(nodes),
        }
        save_row(row, args.out)
        print(f"  {row['phase']}: {ok} ok, {errors} errors | {row['throughput']} ops/s | "
              f"avg {row['avg_ms']} ms, p50 {row['p50_ms']}, p95 {row['p95_ms']}, p99 {row['p99_ms']} | "
              f"client CPU {row['client_cpu_pct']}% | keys per store {row['keys_per_store']}")


if __name__ == "__main__":
    main()
