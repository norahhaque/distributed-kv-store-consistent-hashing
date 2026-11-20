"""Turn the benchmark CSV files into graphs and tables for the report.
Authors: Norah, Aymah

Reads:   results/main.csv, results/sweep.csv, results/main_procs3.csv (made by run_experiments.sh)
Writes:  results/fig1_throughput.png      throughput vs number of stores (SET and GET)
         results/fig2_latency.png         p50 / p95 / p99 latency vs number of stores
         results/fig3_sweep.png           throughput vs number of users, one line per store count
         results/fig4_procs3.png          main experiment vs stronger benchmark (3 processes)
         results/summary.md               all the numbers as markdown tables

Run: python plot_results.py      (needs: pip install -r requirements-dev.txt)

Every number shown is the MEDIAN over the trials (the middle value, so one unlucky
run can't drag it around); error bars show the lowest and highest trial.
"""
import csv
import statistics
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")  # draw straight to PNG files, no window needed
import matplotlib.pyplot as plt

# Colors (colorblind-checked: blue, orange, aqua). Color ALWAYS means the number of stores,
# in every figure, so a reader never has to re-learn it. SET and GET are separate panels.
STORE_COLOR = {1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a"}
STORE_MARKER = {1: "o", 2: "s", 3: "^"}  # different shapes too, so color is never the only clue
TEXT, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({
    "figure.dpi": 150, "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": TEXT,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "axes.axisbelow": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "legend.frameon": False,
})


# ---------------------------------------------------------------- reading the data

def load(path):
    """Read a results CSV into a list of dicts, with numbers converted to numbers."""
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for col in ("nodes", "threads", "trial", "ok", "errors"):
            r[col] = int(r[col])
        for col in ("throughput", "avg_ms", "p50_ms", "p95_ms", "p99_ms", "client_cpu_pct"):
            r[col] = float(r[col])
    return rows


def group(rows, *cols):
    """Group rows by the given columns, e.g. group(rows, "phase", "nodes")[("SET", 3)] -> [rows]."""
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(r[c] for c in cols)].append(r)
    return groups


def med(rows, col):
    return statistics.median(r[col] for r in rows)


def spread(rows, col):
    """(median, distance down to lowest trial, distance up to highest trial) for error bars."""
    m = med(rows, col)
    values = [r[col] for r in rows]
    return m, m - min(values), max(values) - m


# ---------------------------------------------------------------- figures

def fig_throughput(main):
    g = group(main, "phase", "nodes")
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.8), sharey=True)
    for ax, phase in zip(axes, ("SET", "GET")):
        stats = [spread(g[(phase, n)], "throughput") for n in (1, 2, 3)]
        bars = ax.bar([1, 2, 3], [s[0] for s in stats], 0.6, color=[STORE_COLOR[n] for n in (1, 2, 3)],
                      yerr=[[s[1] for s in stats], [s[2] for s in stats]], capsize=3,
                      error_kw={"ecolor": MUTED, "elinewidth": 1})
        ax.bar_label(bars, labels=[f"{s[0]:,.0f}" for s in stats], padding=6, color=TEXT, fontsize=8)
        ax.set_xticks([1, 2, 3], ["1 store", "2 stores", "3 stores"])
        ax.set_title(phase, loc="left", color=TEXT)
    axes[0].set_ylabel("Throughput (operations / second)")
    axes[0].set_ylim(0, axes[0].get_ylim()[1] * 1.1)  # headroom for the value labels
    fig.suptitle("Throughput vs. number of stores (24 users, median of 5 trials; bars show range)",
                 x=0.01, ha="left", color=TEXT)
    fig.tight_layout()
    fig.savefig("results/fig1_throughput.png")
    plt.close(fig)


def fig_latency(main):
    """For each percentile (p50, p95, p99), one bar per store count."""
    g = group(main, "phase", "nodes")
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.6), sharey=True)
    width = 0.26
    pct_cols = ("p50_ms", "p95_ms", "p99_ms")
    for ax, phase in zip(axes, ("SET", "GET")):
        for i, n in enumerate((1, 2, 3)):
            xs = [x + (i - 1) * width for x in range(len(pct_cols))]
            vals = [med(g[(phase, n)], col) for col in pct_cols]
            ax.bar(xs, vals, width - 0.03, color=STORE_COLOR[n], label=f"{n} store{'s' if n > 1 else ''}")
        ax.set_xticks(range(len(pct_cols)), ["p50 (typical)", "p95", "p99 (slowest 1%)"])
        ax.set_title(phase, loc="left", color=TEXT)
    axes[0].set_ylabel("Latency (ms, lower is better)")
    axes[0].legend(loc="upper left")
    fig.suptitle("Latency percentiles vs. number of stores (24 users, median of 5 trials)",
                 x=0.01, ha="left", color=TEXT)
    fig.tight_layout()
    fig.savefig("results/fig2_latency.png")
    plt.close(fig)


def fig_sweep(sweep):
    g = group(sweep, "phase", "nodes", "threads")
    threads = sorted({r["threads"] for r in sweep})
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.6), sharey=True)
    for ax, phase in zip(axes, ("SET", "GET")):
        for n in (1, 2, 3):
            ys = [med(g[(phase, n, t)], "throughput") for t in threads]
            ax.plot(threads, ys, color=STORE_COLOR[n], marker=STORE_MARKER[n], markersize=6,
                    linewidth=2, label=f"{n} store{'s' if n > 1 else ''}")
        ax.set_xscale("log", base=2)  # 1, 3, 6, 12, 24, 48 spread out evenly
        ax.set_xticks(threads, [str(t) for t in threads])
        ax.minorticks_off()
        ax.set_xlabel("Simultaneous users (threads)")
        ax.set_title(phase, loc="left", color=TEXT)
    axes[0].set_ylabel("Throughput (operations / second)")
    axes[0].legend(loc="upper left")
    fig.suptitle("Throughput vs. load (median of 3 trials)", x=0.01, ha="left", color=TEXT)
    fig.tight_layout()
    fig.savefig("results/fig3_sweep.png")
    plt.close(fig)


def fig_procs3(main, procs3):
    """GET and SET throughput: normal benchmark (2 processes) vs stronger one (3 processes)."""
    gm, gp = group(main, "phase", "nodes"), group(procs3, "phase", "nodes")
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.6), sharey=True)
    width = 0.36
    # Neutral grays: these bars compare two benchmark setups, not store counts
    setups = (("2 benchmark processes (main)", gm, "#a3a29c"),
              ("3 benchmark processes (check)", gp, "#52514e"))
    for ax, phase in zip(axes, ("SET", "GET")):
        for i, (label, g, color) in enumerate(setups):
            xs = [n + (i - 0.5) * width for n in (1, 2, 3)]
            vals = [med(g[(phase, n)], "throughput") for n in (1, 2, 3)]
            bars = ax.bar(xs, vals, width - 0.04, color=color, label=label)
            ax.bar_label(bars, labels=[f"{v:,.0f}" for v in vals], padding=3, color=TEXT, fontsize=7)
        ax.set_xticks([1, 2, 3], ["1 store", "2 stores", "3 stores"])
        ax.set_title(phase, loc="left", color=TEXT)
    axes[0].set_ylabel("Throughput (operations / second)")
    axes[0].set_ylim(0, axes[0].get_ylim()[1] * 1.15)
    axes[0].legend(loc="upper left", fontsize=8)
    fig.suptitle("Does a stronger benchmark change the result? (24 users, medians)",
                 x=0.01, ha="left", color=TEXT)
    fig.tight_layout()
    fig.savefig("results/fig4_procs3.png")
    plt.close(fig)


# ---------------------------------------------------------------- tables

def summary(main, sweep, procs3):
    lines = []
    g = group(main, "phase", "nodes")
    lines += ["## Main experiment (24 users, 10,000 keys, median of 5 trials; range = lowest-highest trial)", "",
              "| Phase | Stores | Throughput (ops/s) | Range | Speedup vs 1 store | Avg ms | p50 ms | p95 ms | p99 ms | Errors |",
              "| ----- | ------ | ------------------ | ----- | ------------------ | ------ | ------ | ------ | ------ | ------ |"]
    for phase in ("SET", "GET"):
        base = med(g[(phase, 1)], "throughput")
        for n in (1, 2, 3):
            rs = g[(phase, n)]
            tp = [r["throughput"] for r in rs]
            lines.append(f"| {phase} | {n} | {med(rs, 'throughput'):,.0f} | {min(tp):,.0f}-{max(tp):,.0f} | "
                         f"{med(rs, 'throughput') / base:.2f}x | {med(rs, 'avg_ms'):.2f} | {med(rs, 'p50_ms'):.2f} | "
                         f"{med(rs, 'p95_ms'):.2f} | {med(rs, 'p99_ms'):.2f} | {sum(r['errors'] for r in rs)} |")

    lines += ["", "## Little's Law check: throughput = users / average latency", "",
              "| Phase | Stores | Measured (ops/s) | Predicted 24 / avg latency | Difference |",
              "| ----- | ------ | ---------------- | -------------------------- | ---------- |"]
    for phase in ("SET", "GET"):
        for n in (1, 2, 3):
            rs = g[(phase, n)]
            measured, predicted = med(rs, "throughput"), 24 / (med(rs, "avg_ms") / 1000)
            lines.append(f"| {phase} | {n} | {measured:,.0f} | {predicted:,.0f} | "
                         f"{100 * (predicted - measured) / measured:+.1f}% |")

    lines += ["", "## Keys per store (main experiment)", ""]
    for n in (1, 2, 3):
        lines.append(f"- {n} store(s): {g[('SET', n)][0]['keys_per_store']}")

    gs = group(sweep, "phase", "nodes", "threads")
    threads = sorted({r["threads"] for r in sweep})
    for phase in ("SET", "GET"):
        lines += ["", f"## Thread sweep, {phase}: throughput in ops/s (p50 latency in ms), median of 3 trials", "",
                  "| Users | 1 store | 2 stores | 3 stores |", "| ----- | ------- | -------- | -------- |"]
        for t in threads:
            cells = [f"{med(gs[(phase, n, t)], 'throughput'):,.0f} ({med(gs[(phase, n, t)], 'p50_ms'):.1f})"
                     for n in (1, 2, 3)]
            lines.append(f"| {t} | " + " | ".join(cells) + " |")

    gp = group(procs3, "phase", "nodes")
    lines += ["", "## Stronger benchmark check (3 processes, 3 CPUs; median of 3 trials) vs main", "",
              "| Phase | Stores | Main (ops/s) | 3-process check (ops/s) | Change |",
              "| ----- | ------ | ------------ | ----------------------- | ------ |"]
    for phase in ("SET", "GET"):
        for n in (1, 2, 3):
            a, b = med(g[(phase, n)], "throughput"), med(gp[(phase, n)], "throughput")
            lines.append(f"| {phase} | {n} | {a:,.0f} | {b:,.0f} | {100 * (b - a) / a:+.0f}% |")

    with open("results/summary.md", "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main_rows = load("results/main.csv")
    sweep_rows = load("results/sweep.csv")
    procs3_rows = load("results/main_procs3.csv")
    fig_throughput(main_rows)
    fig_latency(main_rows)
    fig_sweep(sweep_rows)
    fig_procs3(main_rows, procs3_rows)
    summary(main_rows, sweep_rows, procs3_rows)
    print("saved results/fig1-4 *.png and results/summary.md")
