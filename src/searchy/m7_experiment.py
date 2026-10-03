"""Runner for the Stage 4 improvement experiments (M7.1–M7.4).

Implements M7.1–M7.4 (ROADMAP Stage 4: improvements, proven). Protocol
mirrors the committed M4-L table exactly (10 seeds × 100 iterations,
m = n ants, literature parameter defaults, nothing tuned) so every M7
variant is directly comparable to the M4-L rows committed in
experiments/results/m4l-tsp/runs.csv.

Variants (all on top of AS, ± 2-opt, mirroring the table's structure):
- M7.1 nn_init:  AS starting from the NN-tour prior (nn_init=True)
- M7.2 restart:  AS with stagnation restart every 25 no-improvement iters
- M7.3 cand-k20: candidate-list transitions, k=20 (largest instance focus)
- M7.4 combined: AS + nn_init + restart + candidates (the "improved AS")

Each variant runs as (variant, +2opt) pairs; p-values are computed
against the committed M4-L baseline rows (same seeds, same protocol)
via the shared Wilcoxon harness. The claim language (M7.4's GATE:
"X improved Y by Z% (p<0.05, n=30)" at whatever seed count the honest
protocol supports — here n=10, stated) comes from summary.json.

CLI::

    uv run python -m searchy.m7_experiment <variant> [config]
    variants: nn_init | restart | cand | combined
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from searchy.metrics import rank_sum_pvalue
from searchy.tsp import STAGE3_INSTANCES, gap_percent, load_named
from searchy.tsp_aco import (
    _eta_matrix,
    run_as_timed,
)

SEEDS = list(range(10))
N_ITERATIONS = 100
BASELINE_RUNS = Path("experiments/results/m4l-tsp/runs.csv")


def _run_variant(
    variant: str,
    dist: np.ndarray,
    n_ants: int,
    seed: int,
    local_search: bool,
) -> tuple[Any, Any, dict]:
    """One run of one variant; local_search selects the ±2opt pairing."""
    kwargs: dict[str, Any] = {}
    if variant == "nn_init":
        return run_as_timed(
            dist, n_ants, N_ITERATIONS, seed,
            local_search=local_search, nn_init=True,
        )
    if variant == "restart":
        return run_as_timed(
            dist, n_ants, N_ITERATIONS, seed,
            local_search=local_search, restart_threshold=25,
        )
    if variant == "cand":
        return _run_as_cand(
            dist, n_ants, N_ITERATIONS, seed,
            local_search=local_search, k=20,
        )
    if variant == "combined":
        r, s, snaps = _run_as_cand(
            dist, n_ants, N_ITERATIONS, seed,
            local_search=local_search, k=20, nn_init=True, restart_threshold=25,
        )
        return r, s, snaps
    raise ValueError(f"unknown variant {variant!r}")


def _run_as_cand(
    dist: np.ndarray,
    n_ants: int,
    n_iterations: int,
    seed: int,
    *,
    local_search: bool = False,
    k: int = 20,
    nn_init: bool = False,
    restart_threshold: int | None = None,
):
    """AS with candidate-list transitions (M7.3): each step samples from
    the k nearest unvisited cities when pheromone mass concentrates.

    Candidate lists are the literature's runtime device for large
    instances (Dorigo & Stützle ch.3): transition scores are zeroed
    outside the k nearest neighbors of the current city; a city is
    forced in only when all k candidates are visited. Quality impact is
    measured honestly (sometimes helps, sometimes hurts).
    """
    from searchy.tsp import tour_length, two_opt

    import time as _time

    rng = np.random.default_rng(seed)
    n = dist.shape[0]
    eta = _eta_matrix(dist)
    # candidate sets: k nearest by distance, excluding self
    order = np.argsort(dist, axis=1)[:, 1 : k + 1]  # (n, k)
    tau = np.full((n, n), 1e-6)
    np.fill_diagonal(tau, 0.0)

    if nn_init:
        from searchy.tsp import nearest_neighbor_tour

        nn = min(
            (nearest_neighbor_tour(dist, start=s) for s in range(n)),
            key=lambda t: tour_length(t, dist),
        )
        edges = np.stack([nn, np.roll(nn, -1)])
        tau[edges[0], edges[1]] += 1e-6
        tau[edges[1], edges[0]] += 1e-6

    best_tour = None
    best_length = np.iinfo(np.int64).max
    best_iteration = 0
    history_best = np.empty(n_iterations, dtype=np.int64)
    history_mean = np.empty(n_iterations, dtype=np.float64)
    construct_s = 0.0
    ls_s = 0.0
    since_improvement = 0

    for it in range(n_iterations):
        t0 = _time.perf_counter()
        tours = []
        for _ in range(n_ants):
            tour = np.empty(n, dtype=np.int64)
            current = int(rng.integers(n))
            tour[0] = current
            visited = np.zeros(n, dtype=bool)
            visited[current] = True
            for step in range(1, n):
                cand = order[current]
                scores = tau[current, cand] ** 1.0 * eta[current, cand] ** 5.0
                alive = ~visited[cand]
                if alive.any():
                    scores = np.where(alive, scores, 0.0)
                    nxt = int(rng.choice(cand, p=scores / scores.sum()))
                else:
                    # all candidates visited: fall back to nearest unvisited
                    d = dist[current].copy()
                    d[visited] = np.iinfo(np.int32).max
                    nxt = int(np.argmin(d))
                tour[step] = nxt
                visited[nxt] = True
                current = nxt
            tours.append(tour)
        construct_s += _time.perf_counter() - t0
        if local_search:
            t0 = _time.perf_counter()
            tours = [two_opt(t, dist) for t in tours]
            ls_s += _time.perf_counter() - t0
        lengths = np.array([tour_length(t, dist) for t in tours])
        history_mean[it] = lengths.mean()
        it_best = int(np.argmin(lengths))
        if lengths[it_best] < best_length:
            best_length = int(lengths[it_best])
            best_tour = tours[it_best].copy()
            best_iteration = it + 1
            since_improvement = 0
        else:
            since_improvement += 1
        history_best[it] = best_length

        tau *= 0.5
        for t, l in zip(tours, lengths):
            deposit = 100.0 / l
            edges = np.stack([t, np.roll(t, -1)])
            tau[edges[0], edges[1]] += deposit
            tau[edges[1], edges[0]] += deposit
        if restart_threshold is not None and since_improvement >= restart_threshold:
            tau = np.full((n, n), 1e-6)
            np.fill_diagonal(tau, 0.0)
            since_improvement = 0

    assert best_tour is not None
    from searchy.tsp_aco import ACORunStats, ASResult

    result = ASResult(
        best_tour=best_tour,
        best_length=best_length,
        best_iteration=best_iteration,
        history_best=history_best,
        history_mean=history_mean,
        n_ants=n_ants,
        n_iterations=n_iterations,
    )
    stats = ACORunStats(construction_seconds=construct_s, local_search_seconds=ls_s)
    return result, stats, {}


def run(variant: str, instances: list[str] | None = None) -> None:
    instances = instances or list(STAGE3_INSTANCES)
    baseline = pd.read_csv(BASELINE_RUNS)
    out_dir = Path(f"experiments/results/m7-{variant}")
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    t_start = time.perf_counter()
    for name in instances:
        inst = load_named(name, "data/tsplib")
        for ls in (False, True):
            for seed in SEEDS:
                result, stats, _ = _run_variant(
                    variant, inst.dist, inst.n, seed, ls
                )
                rows.append(
                    {
                        "instance": name,
                        "seed": seed,
                        "method": f"AS-{variant}{'+2opt' if ls else ''}",
                        "best_length": result.best_length,
                        "best_iteration": result.best_iteration,
                        "gap_percent": gap_percent(result.best_length, inst.known_optimum),
                        "construct_s": stats.construction_seconds,
                        "ls_s": stats.local_search_seconds,
                        "n_ants": inst.n,
                        "n_iterations": N_ITERATIONS,
                        "known_optimum": inst.known_optimum,
                    }
                )
                print(
                    f"{name} {'+2opt' if ls else '    '} seed={seed} "
                    f"AS-{variant}: {result.best_length} "
                    f"({gap_percent(result.best_length, inst.known_optimum):.2f}%)",
                    flush=True,
                )
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "runs.csv", index=False)

    # p-values vs the committed M4-L AS rows (same seeds, same protocol)
    verdict = {}
    for name in instances:
        sub = df[df.instance == name]
        base = baseline[baseline.instance == name]
        v = {}
        for ls in (False, True):
            label = f"AS-{variant}{'+2opt' if ls else ''}"
            ref = "AS+2opt" if ls else "AS"
            a = sub[sub.method == label].sort_values("seed").best_length.values
            b = base[base.method == ref].sort_values("seed").best_length.values
            if len(a) == len(b) == len(SEEDS):
                p = rank_sum_pvalue(a, b)
                delta = float(np.median(b) - np.median(a))  # positive = variant better
                v[label] = {
                    "median_gap_variant": float(np.median(
                        sub[sub.method == label].gap_percent.values)),
                    "median_gap_baseline": float(np.median(
                        base[base.method == ref].gap_percent.values)),
                    "median_delta_length": delta,
                    "p_vs_baseline": float(p),
                    "n_seeds": len(SEEDS),
                }
        verdict[name] = v

    summary = {
        "protocol": {
            "seeds": SEEDS, "n_iterations": N_ITERATIONS, "n_ants": "m = n",
            "baseline": "committed M4-L runs.csv (identical protocol)",
            "stats": "Wilcoxon rank-sum, tie-corrected normal approx",
            "params": "literature defaults; nothing tuned",
        },
        "variant": variant,
        "verdict": verdict,
        "wall_seconds": time.perf_counter() - t_start,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(f"\ndone: {out_dir / 'summary.json'}")
    print(json.dumps(verdict, indent=1))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("nn_init", "restart", "cand", "combined"):
        sys.exit("usage: uv run python -m searchy.m7_experiment <nn_init|restart|cand|combined>")
    run(sys.argv[1])