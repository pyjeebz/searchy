"""Runner for the lean TSP validation table (M4-L).

Implements M4-L (charter v2/v3: "runner + metrics + Wilcoxon → ONE table:
AS vs MMAS ± 2-opt, 3 instances × 30 seeds, equal construction budget.
GATE: one-command reproducibility").

Protocol — equal budget, paired by seed, nothing tuned:
- Equal CONSTRUCTION budget for all four methods on an instance: same
  n_ants and n_iterations from the config, verbatim. 2-opt is applied
  inside the loop to every ant's tour ("+2opt" variants); construction
  and local-search wall time are measured separately per run (M3.6), so
  the table can attribute quality honestly.
- For each seed s (0..29): AS, AS+2opt, MMAS, MMAS+2opt each run with a
  fresh generator seeded s on the same loaded instance. RNG streams
  diverge across methods by design (different dynamics); the shared
  things — instance, construction rule, budget — are shared.
- Solver parameters are the module defaults (M3.1/M3.5 literature
  settings); nothing is tuned per instance or per method.
- Wilcoxon rank-sum p-values (tie-corrected normal approximation, no
  continuity correction) compare per-seed best lengths for each
  head-to-head pair of methods on each instance.
- NN baseline (best-of-all-starts) is reported per instance for context.

CLI::

    uv run python -m searchy.tsp_experiment experiments/configs/m4l-tsp.yaml
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
from searchy.tsp import (
    STAGE3_INSTANCES,
    KNOWN_OPTIMA,
    gap_percent,
    load_named,
    nearest_neighbor_tour,
    tour_length,
)
from searchy.tsp_aco import run_as_timed, run_mmas_timed

METHOD_KEYS = ("as", "as_2opt", "mmas", "mmas_2opt")
METHOD_LABELS = {
    "as": "AS",
    "as_2opt": "AS+2opt",
    "mmas": "MMAS",
    "mmas_2opt": "MMAS+2opt",
}


def _run_method(
    method: str, dist: np.ndarray, n_ants: int, n_iterations: int, seed: int
):
    ls = method.endswith("2opt")
    if method.startswith("as"):
        return run_as_timed(
            dist, n_ants, n_iterations, seed, local_search=ls
        )
    return run_mmas_timed(
        dist, n_ants, n_iterations, seed, local_search=ls
    )


def run_experiment(config_path: str | Path) -> dict[str, Any]:
    """Execute the full M4-L grid and write results + summary."""
    cfg = yaml.safe_load(Path(config_path).read_text())
    instances: list[str] = cfg.get("instances", list(STAGE3_INSTANCES))
    seeds: list[int] = list(cfg["seeds"])
    n_ants_cfg: Any = cfg.get("n_ants", "n")
    n_iterations: int = int(cfg["n_iterations"])
    method_filter: list[str] | None = cfg.get("method_filter")
    out_dir = Path(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir = Path(cfg.get("figure_dir", out_dir / "figures"))
    fig_dir.mkdir(parents=True, exist_ok=True)

    methods = (
        [m for m in METHOD_KEYS if m in set(method_filter)]
        if method_filter
        else list(METHOD_KEYS)
    )

    rows: list[dict[str, Any]] = []
    t_start = time.perf_counter()
    for name in instances:
        inst = load_named(name, cfg.get("data_dir", "data/tsplib"))
        n_ants = inst.n if n_ants_cfg == "n" else int(n_ants_cfg)
        # NN context row (deterministic; one per instance)
        nn_best = min(
            tour_length(nearest_neighbor_tour(inst.dist, start=s), inst.dist)
            for s in range(inst.n)
        )
        for seed in seeds:
            for method in methods:
                result, stats, _ = _run_method(
                    method, inst.dist, n_ants, n_iterations, seed
                )
                rows.append(
                    {
                        "instance": name,
                        "seed": seed,
                        "method": METHOD_LABELS[method],
                        "best_length": result.best_length,
                        "best_iteration": result.best_iteration,
                        "gap_percent": gap_percent(
                            result.best_length, inst.known_optimum
                        ),
                        "mean_iter_length": float(result.history_mean.mean()),
                        "construct_s": stats.construction_seconds,
                        "ls_s": stats.local_search_seconds,
                        "n_ants": n_ants,
                        "n_iterations": n_iterations,
                        "nn_best": nn_best,
                        "known_optimum": inst.known_optimum,
                        "restarts": getattr(result, "restarts", ()),
                    }
                )
                print(
                    f"{name} seed={seed} {METHOD_LABELS[method]}: "
                    f"{result.best_length} ({gap_percent(result.best_length, inst.known_optimum):.2f}%)",
                    flush=True,
                )

    df = pd.DataFrame(rows)
    runs_name = "runs.csv" if not method_filter else f"runs-{'-'.join(sorted(methods))}.csv"
    df.to_csv(out_dir / runs_name, index=False)

    # --- summary: one table row per (instance, method) + pairwise p-values ---
    present_labels = {METHOD_LABELS[m] for m in methods}
    summary_rows: list[dict[str, Any]] = []
    for name in instances:
        sub = df[df.instance == name]
        opt = int(sub.known_optimum.iloc[0])
        for method in present_labels:
            m = sub[sub.method == method]
            gaps = m.gap_percent.values
            summary_rows.append(
                {
                    "instance": name,
                    "method": method,
                    "mean_length": float(m.best_length.mean()),
                    "std_length": float(m.best_length.std()),
                    "median_gap_percent": float(np.median(gaps)),
                    "mean_gap_percent": float(gaps.mean()),
                    "best_length": int(m.best_length.min()),
                    "worst_length": int(m.best_length.max()),
                    "mean_construct_s": float(m.construct_s.mean()),
                    "mean_ls_s": float(m.ls_s.mean()),
                    "n_seeds": len(m),
                    "known_optimum": opt,
                }
            )
        # head-to-head p-values on per-seed best lengths (only pairs where
        # both methods ran in this pass)
        per = {
            meth: sub[sub.method == METHOD_LABELS[meth]].sort_values("seed")
            for meth in methods
        }
        pairs = [
            ("as_2opt", "as"),
            ("mmas_2opt", "mmas"),
            ("mmas", "as"),
            ("mmas_2opt", "as_2opt"),
        ]
        for a, b in pairs:
            if a not in per or b not in per:
                continue
            la = per[a].best_length.values
            lb = per[b].best_length.values
            if len(la) == 0 or len(lb) == 0:
                continue
            summary_rows.append(
                {
                    "instance": name,
                    "method": f"p[{METHOD_LABELS[a]} vs {METHOD_LABELS[b]}]",
                    "mean_length": float("nan"),
                    "std_length": float("nan"),
                    "median_gap_percent": float("nan"),
                    "mean_gap_percent": rank_sum_pvalue(la, lb),
                    "best_length": 0,
                    "worst_length": 0,
                    "mean_construct_s": float("nan"),
                    "mean_ls_s": float("nan"),
                    "n_seeds": len(la),
                    "known_optimum": opt,
                }
            )
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(out_dir / "summary.csv", index=False)

    wall = time.perf_counter() - t_start
    summary = {
        "protocol": {
            "instances": instances,
            "seeds": seeds,
            "n_seeds": len(seeds),
            "n_ants": str(n_ants_cfg),
            "n_iterations": n_iterations,
            "equal_construction_budget": True,
            "stats": "Wilcoxon rank-sum, tie-corrected normal approx, no continuity correction",
            "params": "module defaults (M3.1/M3.5 literature settings), nothing tuned",
        },
        "wall_seconds": wall,
        "table": summary_df.to_dict(orient="records"),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(f"\nDone in {wall/60:.1f} min. Table: {out_dir / 'summary.csv'}")
    return summary


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: uv run python -m searchy.tsp_experiment <config.yaml>")
    run_experiment(sys.argv[1])