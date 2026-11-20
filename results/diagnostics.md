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
