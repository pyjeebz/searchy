"""Runner for the router-vs-baselines comparison experiment.

Implements M6.5 (ROADMAP: "100 queries x 5 seeds, all methods, same query
stream"; config: ``experiments/configs/m6.5-comparison.yaml``).

Protocol — equal budget, paired by seed:
- ONE query stream (``query_seed``) shared by every method and every seed,
  per the charter's honesty rule (same query stream for all compared
  methods).
- For each seed ``s`` every method runs the full stream with a fresh
  generator seeded ``s``. Methods consume their generators differently, so
  call-noise draws differ across methods; the shared things (stream, pool,
  reward function, noise model) are shared. See baselines.py's docstring.
- Nothing is tuned here: router parameters come from the config verbatim.

DoD (ROADMAP M6.5), computed and reported whatever it turns out to be:
(a) the router's cumulative reward beats greedy-advertised on >= 4/5
seeds; (b) the router's mean per-query utility lands within 10% of the
oracle's. Failures are reported as measured negative results, not patched.

CLI::

    uv run python -m searchy.experiment experiments/configs/m6.5-comparison.yaml
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
import yaml

from searchy.baselines import run_baseline
from searchy.metrics import rolling_mean, summarize_run
from searchy.queries import generate_queries
from searchy.router import PheromoneRouter
from searchy.tools import build_tool_pool
from searchy.viz import convergence_plot

ROUTER = "pheromone_router"
GREEDY = "greedy-advertised"
ORACLE = "oracle"

_REQUIRED_KEYS = ("n_per_type", "query_seed", "seeds", "methods")


def load_config(path: str) -> dict[str, Any]:
    """Load and validate an experiment YAML config."""
    with open(path) as f:
        config: dict[str, Any] = yaml.safe_load(f)
    missing = [key for key in _REQUIRED_KEYS if key not in config]
    if missing:
        raise ValueError(f"config {path} is missing required keys: {missing}")
    return config


def run_method(
    name: str,
    pool: dict,
    queries: Sequence,
    seed: int,
    router_params: dict[str, Any],
) -> list[Any]:
    """Run one method over the full stream with a generator seeded ``seed``."""
    rng = np.random.default_rng(seed)
    if name == ROUTER:
        router = PheromoneRouter(pool, **router_params)
        return router.route_stream(queries, rng)
    return run_baseline(name, pool, queries, rng)


def record_rows(method: str, seed: int, records: Sequence[Any]) -> list[dict[str, Any]]:
    """Flatten one run into long-format CSV rows (one per query)."""
    return [
        {
            "seed": seed,
            "method": method,
            "query_index": index,
            "query_type": record.query.qtype.value,
            "retrieve_tool": record.path[0],
            "process_tool": record.path[1],
            "reward": record.reward,
            "cost_tokens": sum(r.cost_tokens for r in record.results),
            "latency_ms": sum(r.latency_ms for r in record.results),
        }
        for index, record in enumerate(records)
    ]


def compute_verdict(per_run: list[dict[str, Any]], seeds: Sequence[int]) -> dict[str, Any]:
    """The M6.5 DoD checks, pass or fail — never tuned to pass."""
    cumulative = {(run["method"], run["seed"]): run["cumulative_reward"] for run in per_run}
    per_seed = [
        {
            "seed": seed,
            "router_cumulative": cumulative[(ROUTER, seed)],
            "greedy_cumulative": cumulative[(GREEDY, seed)],
            "router_wins": cumulative[(ROUTER, seed)] > cumulative[(GREEDY, seed)],
        }
        for seed in seeds
        if (ROUTER, seed) in cumulative and (GREEDY, seed) in cumulative
    ]
    wins = sum(int(s["router_wins"]) for s in per_seed)
    required = max(1, math.ceil(0.8 * len(per_seed)))  # >= 4 of 5

    def mean_utility(method: str) -> float:
        utils = [
            run["mean_reward"] for run in per_run if run["method"] == method
        ]
        return float(np.mean(utils)) if utils else float("nan")

    router_utility = mean_utility(ROUTER)
    oracle_utility = mean_utility(ORACLE)
    within = router_utility >= 0.9 * oracle_utility
    return {
        "beats_greedy_advertised": {
            "wins": wins,
            "required": required,
            "n_seeds": len(per_seed),
            "per_seed": per_seed,
            "met": wins >= required,
        },
        "within_10pct_of_oracle": {
            "router_mean_utility": router_utility,
            "oracle_mean_utility": oracle_utility,
            "ratio": router_utility / oracle_utility,
            "met": bool(within),
        },
        "dod_met": bool(wins >= required and within),
    }


def run_experiment(config: dict[str, Any]) -> dict[str, Any]:
    """Run every (method, seed) pair and aggregate. Deterministic given the
    config: same config in, same numbers out."""
    pool = build_tool_pool()
    stream_rng = np.random.default_rng(config["query_seed"])
    queries = generate_queries(stream_rng, n_per_type=config["n_per_type"])
    router_params = config.get("router", {})
    window = config.get("rolling_window", 10)

    rows: list[dict[str, Any]] = []
    per_run: list[dict[str, Any]] = []
    curves: dict[str, dict[int, np.ndarray]] = {}
    for seed in config["seeds"]:
        for method in config["methods"]:
            records = run_method(method, pool, queries, seed, router_params)
            rows.extend(record_rows(method, seed, records))
            per_run.append({"method": method, "seed": seed, **summarize_run(records)})
            curves.setdefault(method, {})[seed] = rolling_mean(
                [r.reward for r in records], window
            )

    frame = pd.DataFrame(rows)
    per_type = {
        f"{method}|{qtype}": float(group["reward"].mean())
        for (method, qtype), group in frame.groupby(["method", "query_type"])
    }
    return {
        "config": config,
        "rows": rows,
        "per_run": per_run,
        "curves": curves,
        "per_type_mean_reward": per_type,
        "verdict": compute_verdict(per_run, config["seeds"]),
    }


def method_means(per_run: list[dict[str, Any]], methods: Sequence[str]) -> list[dict[str, Any]]:
    """Across-seed mean/std per method for the headline table."""
    out = []
    for method in methods:
        runs = [run for run in per_run if run["method"] == method]
        cumulative = np.array([run["cumulative_reward"] for run in runs])
        out.append(
            {
                "method": method,
                "n_seeds": len(runs),
                "cumulative_reward_mean": float(cumulative.mean()),
                "cumulative_reward_std": float(cumulative.std()),
                "mean_reward": float(np.mean([run["mean_reward"] for run in runs])),
                "final_quality": float(np.mean([run["final_quality"] for run in runs])),
                "mean_cost_tokens": float(np.mean([run["mean_cost_tokens"] for run in runs])),
                "mean_latency_ms": float(np.mean([run["mean_latency_ms"] for run in runs])),
            }
        )
    return out


def write_outputs(results: dict[str, Any]) -> None:
    """Write records CSV, per-run CSV, summary JSON, and the convergence
    figure. Paths come from the config (cwd-relative)."""
    config = results["config"]
    out_dir = Path(config["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(results["rows"]).to_csv(out_dir / "records.csv", index=False)
    pd.DataFrame(results["per_run"]).to_csv(out_dir / "summary.csv", index=False)

    summary = {
        "protocol": {
            "n_queries": 4 * config["n_per_type"],
            "query_seed": config["query_seed"],
            "seeds": config["seeds"],
            "router_params": config.get("router", {}),
            "rolling_window": config.get("rolling_window", 10),
            "note": (
                "one shared query stream; per seed every method runs it with "
                "a fresh generator seeded s; call-noise draws differ across "
                "methods by construction (see baselines.py docstring)"
            ),
        },
        "method_means": method_means(results["per_run"], config["methods"]),
        "per_type_mean_reward": results["per_type_mean_reward"],
        "verdict": results["verdict"],
    }
    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    curves = {
        method: np.mean([c for c in by_seed.values()], axis=0)
        for method, by_seed in results["curves"].items()
    }
    router_band = None
    if ROUTER in results["curves"]:
        stacked = np.stack(list(results["curves"][ROUTER].values()))
        router_band = (stacked.min(axis=0), stacked.max(axis=0))
    convergence_plot(
        curves,
        router_band,
        window=config.get("rolling_window", 10),
        out_path=config["figure"],
        title=f"Searchy {config.get('name', 'M6.5')} — learning curves "
        f"(mean over {len(config['seeds'])} seeds)",
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m searchy.experiment <config.yaml>", file=sys.stderr)
        return 2
    config = load_config(args[0])
    results = run_experiment(config)
    write_outputs(results)

    verdict = results["verdict"]
    beats = verdict["beats_greedy_advertised"]
    oracle = verdict["within_10pct_of_oracle"]
    print(
        f"beats greedy-advertised on {beats['wins']}/{beats['n_seeds']} seeds "
        f"(required {beats['required']}) -> {'MET' if beats['met'] else 'NOT MET'}"
    )
    print(
        f"router mean utility {oracle['router_mean_utility']:+.4f} vs oracle "
        f"{oracle['oracle_mean_utility']:+.4f} (ratio {oracle['ratio']:.3f}) -> "
        f"{'within' if oracle['met'] else 'outside'} 10%"
    )
    print(f"overall DoD: {'MET' if verdict['dod_met'] else 'NOT MET'}")
    print(f"outputs: {config['output_dir']}/ and {config['figure']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())