#!/bin/bash
# Runs every benchmark experiment for the report. Authors: Norah, Aymah
#
#   ./run_experiments.sh          (Docker must be running; takes ~30-40 minutes)
#
# Part 1, main experiment:  1, 2, 3 stores x 5 trials, 24 threads  -> results/main.csv
# Part 2, thread sweep:     1, 2, 3 stores x 1..48 threads x 3 trials -> results/sweep.csv
# Everything printed is also saved to results/experiment_log.txt

set -e                  # stop immediately if any command fails
cd "$(dirname "$0")"    # run from the project folder, wherever the script is started from

TRIALS=5                # repeats per configuration in the main experiment
KEYS=10000              # keys per phase in the main experiment
THREADS=24              # simultaneous users in the main experiment
PROCS=2                 # benchmark processes (matches the bench container's 2 CPUs)
SWEEP_THREADS="1 3 6 12 24 48"
SWEEP_TRIALS=3
SWEEP_KEYS=6000         # fewer keys so the sweep finishes in reasonable time

mkdir -p results
rm -f results/main.csv results/sweep.csv   # start fresh (old runs would mix in)
exec > >(tee results/experiment_log.txt) 2>&1   # copy all output into the log file

# Wipe all stores and data, then start only the first N stores (kv1, or kv1+kv2, or all three)
fresh_start() {
    docker compose down -v >/dev/null 2>&1
    case $1 in
        1) docker compose up -d kv1 >/dev/null 2>&1 ;;
        2) docker compose up -d kv1 kv2 >/dev/null 2>&1 ;;
        3) docker compose up -d kv1 kv2 kv3 >/dev/null 2>&1 ;;
    esac
}

# Run the benchmark inside Docker (all arguments are passed on to kv_bench.py)
bench() {
    docker compose run --rm bench python kv_bench.py --docker --procs $PROCS "$@" 2>&1 \
        | grep -v "^ Container\|Creating\|Created"   # hide Docker's own status lines
}

echo "Started $(date). Docker CPUs: $(docker info --format '{{.NCPU}}')"
docker compose build >/dev/null 2>&1   # make sure the image has the latest code

echo "=== Part 1: main experiment ($TRIALS trials) ==="
# Trials are the OUTER loop, so 1/2/3 stores take turns. If the laptop gets busier or
# quieter over time, that affects every configuration equally instead of just one.
for trial in $(seq 1 $TRIALS); do
    for nodes in 1 2 3; do
        fresh_start $nodes
        bench --nodes $nodes --keys $KEYS --threads $THREADS --trial $trial --out results/main.csv
    done
done

echo "=== Part 2: thread sweep ($SWEEP_TRIALS trials) ==="
for trial in $(seq 1 $SWEEP_TRIALS); do
    for threads in $SWEEP_THREADS; do
        for nodes in 1 2 3; do
            fresh_start $nodes
            bench --nodes $nodes --keys $SWEEP_KEYS --threads $threads --trial $trial --out results/sweep.csv
        done
    done
done

docker compose down -v >/dev/null 2>&1
echo "Finished $(date)"
