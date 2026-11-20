# Benchmark diagnostics (Phase 7, 2026-11-20)

Mac: 8 cores, 8 GB RAM. Docker Desktop VM: 6 CPUs, 4 GB. Each store container: cpus 1.0.

## 1. Benchmark on the laptop (through Docker Desktop port forwarding): more stores looked SLOWER
24 threads, 10,000 keys, 1 process (raw rows: diag_laptop_client.csv)

| Stores | SET ops/s | GET ops/s | Benchmark CPU |
| ------ | --------- | --------- | ------------- |
| 1      | 818       | 904       | 104-139%      |
| 2      | 405       | 581       | ~100%         |
| 3      | 503       | 500       | ~100%         |

During the runs, stores were NOT busy (1 store: kv1 78%; 3 stores: ~45% each), while Docker Desktop's
networking on the Mac (VirtualMachine + com.docker.backend processes) used ~145-170% CPU.
-> The bottleneck was the Mac-to-container port forwarding, not the stores.
-> Fix: run the benchmark as a container on the same Docker network (bench service).

## 2. Benchmark inside Docker: scaling appears
| Stores | Procs | SET ops/s | GET ops/s |
| ------ | ----- | --------- | --------- |
| 1      | 2     | 558       | 955       |
| 3      | 2     | 1547      | 1774      |

## 3. CPU throttling check (cgroup cpu.stat after a 3-store, 30,000-key run)
nr_throttled 5-9 of ~710 periods; total frozen time 0.08-0.55 s over ~70 s. -> Minor, not the main cause.

## 4. Shared disk (fsync) test: 5 s tight write+fsync loop
| Setup                  | fsyncs/s per container | Total |
| ---------------------- | ---------------------- | ----- |
| kv1 alone              | 1637                   | 1637  |
| kv1, kv2, kv3 at once  | 908 each               | 2724  |
-> All volumes share one virtual disk on one SSD: 3 stores give only ~1.66x write capacity.
   This caps how much SET throughput can scale on one laptop.

## 5. Follow-up: is the benchmark what limits GET at 3 stores? (procs 3, bench 3 CPUs, Docker VM 7 CPUs)
3 trials, 24 threads, 10,000 keys (raw rows: main_procs3.csv). Medians, ops/s:

| Setup                          | SET 1 / 2 / 3 stores | GET 1 / 2 / 3 stores |
| ------------------------------ | -------------------- | -------------------- |
| Main (2 procs, 2 CPUs, VM 6)   | 1830 / 2403 / 2908   | 1946 / 3533 / 3149   |
| Follow-up (3 procs, 3 CPUs, VM 7) | 1865 / 2439 / 2782 | 2117 / 3968 / 3945   |

A stronger benchmark raised GET by ~12% at 2 stores and ~25% at 3 stores, but 3 stores still did not beat 2.
CPU sampled during a 3-store GET phase: stores 75-88% of their 1 CPU each, benchmark ~204%.
-> ~4.5 cores busy in containers alone, plus Docker networking. The Mac is an Apple M3 with only
   4 performance cores + 4 slower efficiency cores, so at 3 stores part of the work runs on efficiency cores.
-> Conclusion: for reads, the limit at 3 stores is the laptop as a whole (fast cores shared by stores,
   benchmark and Docker), not one component. The benchmark was part of it, not all of it.
Note: one 40,000-key diagnostic run (not used in results) had 48 GET errors while `docker stats` was sampling;
every run used in the results had 0 errors.
