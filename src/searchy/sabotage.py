"""Runner for the sabotage-adaptation demo (M6.6).

ROADMAP M6.6: "At query #50: web_search true quality drops to 0.05 AND
latency x3. DoD: on >=4/5 seeds, web_search's Layer-1 traffic share falls
below 20% within 30 queries of the event, mean utility recovers to >=90%
of its pre-sabotage rolling average, and we produce the money plot:
per-tool traffic share over query index, with a vertical line at #50.
Save as PNG + GIF."

Protocol — one environment change mid-stream, zero learning-machinery
changes:

- The event is a pure environment change. A replacement Tool (same name,
  cost and advertised skills; true quality floored at the configured
  value for every type; latency multiplied) is swapped into the pool dict
  and the router's cached layer list right before the configured query
  (1-based) is routed. The router's tau, deposits and transition rule are
  untouched — the colony must notice the world changed through realized
  rewards alone, which is the whole demo.
- Baselines face the same event with zero baseline code changes: every
  ``run_baseline`` call re-derives its tool lists from the pool dict, so
  baselines are run as two halves around the swap. greedy-advertised
  keeps trusting the unchanged ads (never adapts, eats the damage
  forever); the oracle re-picks its paths from the true, sabotaged
  profiles (adapts instantly). Same generator across both halves.
- Same shared stream and router parameters as M6.5 (query_seed 100,
  M6.3 values verbatim); one fresh pool per (method, seed) run because
  the event mutates the pool. Nothing is tuned.

DoD operationalization (ROADMAP wording -> measurable clauses):

- share clause: the rolling-window share of the sabotaged tool among
  Layer-1 choices falls strictly below ``share_threshold`` (0.20) at
  some query in the ``adaptation_window`` (30) queries starting with the
  first sabotaged query (queries #50-#79, 0-based indices 49-78).
- recovery clause: the rolling mean reward reaches at least
  ``recovery_fraction`` (0.90) of the pre-sabotage average (mean reward
  over the ``adaptation_window`` queries before the event, #20-#49) at
  some query in that window whose *trailing rolling window is fully
  post-event* (queries #59-#79 in the shipped config). The first run
  showed this restriction is load-bearing: with the check open to every
  window index, all passing seeds "recovered" at #50-#51, before the
  damage had permeated the trailing window — a window-start artifact,
  not recovery (logged as D5 in docs/diagnosis-log.md). Window-start
  passes are still counted, as ``n_pass_incl_window_start``, so the
  artifact stays visible instead of hidden.
- A seed passes only when BOTH clauses hold; the DoD needs >= 4/5 seeds
  (per-clause counts are reported alongside so a lopsided miss stays
  visible). Pre-event shares are reported too: a seed already below the
  threshold before the event makes the share clause vacuous — surfaced,
  never hidden.

The DoD has no negative-result branch, so a miss is reported as measured
(and logged in docs/diagnosis-log.md), never tuned away. D3 flagged this
risk up front: the same lock-in that flattened M6.5 may make a 30-query
recovery slow.

CLI::

    uv run python -m searchy.sabotage experiments/configs/m6.6-sabotage.yaml
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
import yaml

from searchy.baselines import run_baseline
from searchy.experiment import method_means, record_rows
from searchy.metrics import rolling_mean, summarize_run
from searchy.queries import generate_queries
from searchy.router import PheromoneRouter
from searchy.tools import LAYER_RETRIEVE, Tool, build_tool_pool, tools_in_layer
from searchy.viz import money_gif, money_plot

ROUTER = "pheromone_router"

_REQUIRED_KEYS = (
    "n_per_type",
    "query_seed",
    "seeds",
    "methods",
    "sabotage",
    "output_dir",
    "figure",
    "gif",
)
_REQUIRED_SABOTAGE_KEYS = (
    "tool",
    "query",
    "quality",
    "latency_multiplier",
    "adaptation_window",
    "share_threshold",
    "recovery_fraction",
)


@dataclass(frozen=True)
class SabotageSpec:
    """The DoD's environment event, as config data.

    ``query`` is 1-based: the event fires immediately before that query
    is routed, so ``event_index`` (0-based) is the first sabotaged
    position.
    """

    tool_name: str
    query: int
    quality: float
    latency_multiplier: int
    adaptation_window: int
    share_threshold: float
    recovery_fraction: float

    @property
    def event_index(self) -> int:
        return self.query - 1


def load_config(path: str) -> dict[str, Any]:
    """Load and validate an experiment YAML config."""
    with open(path) as f:
        config: dict[str, Any] = yaml.safe_load(f)
    missing = [key for key in _REQUIRED_KEYS if key not in config]
    if missing:
        raise ValueError(f"config {path} is missing required keys: {missing}")
    return config


def spec_from_config(config: dict[str, Any]) -> SabotageSpec:
    """Build the SabotageSpec from the config's ``sabotage`` block."""
    sabotage = config["sabotage"]
    missing = [key for key in _REQUIRED_SABOTAGE_KEYS if key not in sabotage]
    if missing:
        raise ValueError(f"sabotage block is missing required keys: {missing}")
    return SabotageSpec(
        tool_name=str(sabotage["tool"]),
        query=int(sabotage["query"]),
        quality=float(sabotage["quality"]),
        latency_multiplier=int(sabotage["latency_multiplier"]),
        adaptation_window=int(sabotage["adaptation_window"]),
        share_threshold=float(sabotage["share_threshold"]),
        recovery_fraction=float(sabotage["recovery_fraction"]),
    )


def _validate_run(config: dict[str, Any], spec: SabotageSpec) -> None:
    """The DoD windows must fit inside the stream, with a full pre window."""
    n_queries = 4 * config["n_per_type"]
    if not config["seeds"]:
        raise ValueError("seeds must not be empty")
    if ROUTER not in config["methods"]:
        raise ValueError(f"methods must include {ROUTER!r} — the DoD is about the router")
    if spec.query < 1:
        raise ValueError("sabotage.query must be >= 1")
    if spec.adaptation_window < 1:
        raise ValueError("sabotage.adaptation_window must be >= 1")
    if spec.event_index < spec.adaptation_window:
        raise ValueError(
            f"sabotage.query {spec.query} leaves fewer than "
            f"{spec.adaptation_window} pre-event queries for the baseline"
        )
    if spec.event_index + spec.adaptation_window > n_queries:
        raise ValueError(
            f"the stream has {n_queries} queries; the DoD window needs "
            f"queries #{spec.query}..#{spec.query + spec.adaptation_window - 1}"
        )
    window = config.get("rolling_window", 10)
    if window < 1:
        raise ValueError("rolling_window must be >= 1")
    if window > spec.adaptation_window:
        raise ValueError(
            f"rolling_window ({window}) exceeds sabotage.adaptation_window "
            f"({spec.adaptation_window}); the recovery check needs at least "
            "one query whose trailing window is fully post-event"
        )


def make_sabotaged_tool(tool: Tool, spec: SabotageSpec) -> Tool:
    """The post-event replacement: quality floored, latency multiplied.

    Name, layer, cost and advertised skills are carried over unchanged —
    the ads keep claiming everything is fine; only the truth changes.
    """
    return replace(
        tool,
        true_quality={qtype: spec.quality for qtype in tool.true_quality},
        latency_ms=tool.latency_ms * spec.latency_multiplier,
    )


def apply_sabotage(pool: dict[str, Tool], router: PheromoneRouter, spec: SabotageSpec) -> Tool:
    """Swap the sabotaged tool into the world the router lives in.

    The pool dict and the router's cached layer list both hold Tool
    objects, so both must see the replacement. The router's learning
    state (tau) is deliberately untouched — this is an environment
    change, not a router change.
    """
    if spec.tool_name not in pool:
        raise ValueError(f"sabotage target {spec.tool_name!r} not in the pool")
    replacement = make_sabotaged_tool(pool[spec.tool_name], spec)
    pool[spec.tool_name] = replacement
    layer_tools = router.layers[LAYER_RETRIEVE]
    for index, tool in enumerate(layer_tools):
        if tool.name == spec.tool_name:
            layer_tools[index] = replacement
            return replacement
    raise ValueError(f"sabotage target {spec.tool_name!r} not in the retrieve layer")


def run_router_with_event(
    pool: dict[str, Tool],
    queries: Sequence[Any],
    seed: int,
    router_params: dict[str, Any],
    spec: SabotageSpec,
) -> list[Any]:
    """Route the stream with one environment swap at the event index."""
    rng = np.random.default_rng(seed)
    router = PheromoneRouter(pool, **router_params)
    records = []
    for index, query in enumerate(queries):
        if index == spec.event_index:
            apply_sabotage(pool, router, spec)
        records.append(router.route(query, rng))
    return records


def run_baseline_with_event(
    name: str,
    pool: dict[str, Tool],
    queries: Sequence[Any],
    seed: int,
    spec: SabotageSpec,
) -> list[Any]:
    """Run a baseline as two halves around the event (same generator).

    ``run_baseline`` re-derives its tool lists from the pool dict on each
    call, so the second half runs against the sabotaged pool:
    greedy-advertised keeps trusting the unchanged ads, while the oracle
    re-picks its paths from the true (sabotaged) profiles.
    """
    rng = np.random.default_rng(seed)
    event = spec.event_index
    records = list(run_baseline(name, pool, queries[:event], rng))
    pool[spec.tool_name] = make_sabotaged_tool(pool[spec.tool_name], spec)
    records.extend(run_baseline(name, pool, queries[event:], rng))
    return records


def retrieve_share(records: Sequence[Any], tool_name: str, window: int) -> np.ndarray:
    """Rolling share of ``tool_name`` among Layer-1 (retrieve) choices."""
    indicator = [1.0 if record.path[0] == tool_name else 0.0 for record in records]
    return rolling_mean(indicator, window)


def compute_verdict(
    per_seed: list[dict[str, Any]],
    spec: SabotageSpec,
    window: int,
) -> dict[str, Any]:
    """The M6.6 DoD checks, pass or fail — never tuned to pass.

    ``per_seed`` holds one entry per router seed: ``"seed"``, the rolling
    sabotaged-tool Layer-1 share curve (``"share"``) and the raw per-query
    rewards (``"rewards"``). The DoD counts seeds passing BOTH clauses
    (>= 4/5); per-clause counts are reported alongside.

    Recovery is only measured at indices whose trailing rolling window is
    fully post-event: an index in the first ``window - 1`` slots of the
    DoD window still averages mostly pre-event rewards and can pass
    before any damage arrives (D5). Passes at those window-start indices
    are counted separately as ``n_pass_incl_window_start``.
    """
    required = max(1, math.ceil(0.8 * len(per_seed)))
    event = spec.event_index
    post = slice(event, event + spec.adaptation_window)
    pre = slice(max(0, event - spec.adaptation_window), event)
    sustained = slice(event + window - 1, event + spec.adaptation_window)

    per_seed_detail: list[dict[str, Any]] = []
    share_passes = 0
    recovery_passes = 0
    window_start_passes = 0
    both = 0
    for entry in per_seed:
        rewards = np.asarray(entry["rewards"], dtype=float)
        share = np.asarray(entry["share"], dtype=float)
        rolling = rolling_mean(rewards, window)
        pre_baseline = float(rewards[pre].mean())
        target = spec.recovery_fraction * pre_baseline

        below = np.nonzero(share[post] < spec.share_threshold)[0]
        recovered = np.nonzero(rolling[sustained] >= target)[0]
        early = np.nonzero(rolling[post] >= target)[0]
        share_pass = bool(len(below))
        recovery_pass = bool(len(recovered))
        pre_event_share = float(share[pre].mean())
        if share_pass:
            share_passes += 1
        if recovery_pass:
            recovery_passes += 1
        if len(early):
            window_start_passes += 1
        if share_pass and recovery_pass:
            both += 1
        per_seed_detail.append(
            {
                "seed": entry["seed"],
                "pre_event_share": pre_event_share,
                "share_below_before_event": bool(pre_event_share < spec.share_threshold),
                "min_share_in_window": float(share[post].min()),
                "share_pass": share_pass,
                "first_below_query": int(event + below[0] + 1) if share_pass else None,
                "pre_baseline": pre_baseline,
                "recovery_target": target,
                "min_rolling_reward_in_window": float(rolling[sustained].min()),
                "max_rolling_reward_in_window": float(rolling[sustained].max()),
                "recovery_pass": recovery_pass,
                "recovery_query": (
                    int(sustained.start + recovered[0] + 1) if recovery_pass else None
                ),
                "recovery_query_incl_window_start": (
                    int(event + early[0] + 1) if len(early) else None
                ),
                "end_rolling_reward": float(rolling[-1]),
                "passes_both": bool(share_pass and recovery_pass),
            }
        )
    return {
        "event_query": spec.query,
        "window_queries": spec.adaptation_window,
        "rolling_window": window,
        "recovery_measured_from_query": event + window,
        "share_clause": {
            "threshold": spec.share_threshold,
            "n_pass": share_passes,
            "required": required,
            "met": bool(share_passes >= required),
        },
        "recovery_clause": {
            "fraction": spec.recovery_fraction,
            "n_pass": recovery_passes,
            "required": required,
            "met": bool(recovery_passes >= required),
            "n_pass_incl_window_start": window_start_passes,
        },
        "seeds_passing_both": both,
        "dod_met": bool(both >= required),
        "per_seed": per_seed_detail,
    }


def run_demo(config: dict[str, Any]) -> dict[str, Any]:
    """Run every (method, seed) pair around the event and aggregate.

    Deterministic given the config: same config in, same numbers out.
    One fresh pool per (method, seed) run — the event mutates the pool.
    """
    spec = spec_from_config(config)
    _validate_run(config, spec)
    stream_rng = np.random.default_rng(config["query_seed"])
    queries = generate_queries(stream_rng, n_per_type=config["n_per_type"])
    router_params = config.get("router", {})
    window = config.get("rolling_window", 10)
    reference_pool = build_tool_pool()
    retrieve_names = [tool.name for tool in tools_in_layer(reference_pool, LAYER_RETRIEVE)]
    event = spec.event_index

    rows: list[dict[str, Any]] = []
    per_run: list[dict[str, Any]] = []
    pre_post: dict[str, dict[str, list[float]]] = {}
    share_curves: dict[str, dict[int, dict[str, np.ndarray]]] = {}
    reward_curves: dict[str, dict[int, np.ndarray]] = {}
    router_verdict_inputs: list[dict[str, Any]] = []

    for seed in config["seeds"]:
        for method in config["methods"]:
            pool = build_tool_pool()  # fresh: the event mutates the pool
            if method == ROUTER:
                records = run_router_with_event(pool, queries, seed, router_params, spec)
                router_verdict_inputs.append(
                    {
                        "seed": seed,
                        "share": retrieve_share(records, spec.tool_name, window),
                        "rewards": [record.reward for record in records],
                    }
                )
            else:
                records = run_baseline_with_event(method, pool, queries, seed, spec)
            rows.extend(record_rows(method, seed, records))
            per_run.append({"method": method, "seed": seed, **summarize_run(records)})

            rewards = np.array([record.reward for record in records])
            bucket = pre_post.setdefault(method, {"pre": [], "post": []})
            bucket["pre"].append(float(rewards[:event].mean()))
            bucket["post"].append(float(rewards[event:].mean()))
            share_curves.setdefault(method, {})[seed] = {
                name: retrieve_share(records, name, window) for name in retrieve_names
            }
            reward_curves.setdefault(method, {})[seed] = rolling_mean(rewards, window)

    # across-seed means for the money plot, plus the router's seed spread
    mean_shares = {
        method: {
            name: np.mean([shares[name] for shares in by_seed.values()], axis=0)
            for name in retrieve_names
        }
        for method, by_seed in share_curves.items()
    }
    mean_rewards = {
        method: np.mean(list(by_seed.values()), axis=0)
        for method, by_seed in reward_curves.items()
    }
    share_band = None
    reward_band = None
    router_shares = share_curves.get(ROUTER, {})
    router_rewards = reward_curves.get(ROUTER, {})
    if router_shares:
        stacked = np.stack([shares[spec.tool_name] for shares in router_shares.values()])
        share_band = (stacked.min(axis=0), stacked.max(axis=0))
    if router_rewards:
        stacked = np.stack(list(router_rewards.values()))
        reward_band = (stacked.min(axis=0), stacked.max(axis=0))

    return {
        "config": config,
        "spec": spec,
        "rows": rows,
        "per_run": per_run,
        "verdict": compute_verdict(router_verdict_inputs, spec, window),
        "pre_post_mean_reward": {
            method: {
                "pre_event": float(np.mean(vals["pre"])),
                "post_event": float(np.mean(vals["post"])),
            }
            for method, vals in pre_post.items()
        },
        "mean_shares": mean_shares,
        "mean_rewards": mean_rewards,
        "share_band": share_band,
        "reward_band": reward_band,
    }


def write_outputs(results: dict[str, Any]) -> None:
    """Write records CSV, per-run CSV, summary JSON, money plot PNG + GIF.

    Paths come from the config (cwd-relative)."""
    config = results["config"]
    spec = results["spec"]
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
            "sabotage": {
                "tool": spec.tool_name,
                "query": spec.query,
                "quality": spec.quality,
                "latency_multiplier": spec.latency_multiplier,
                "note": (
                    "pure environment change: the replacement Tool (same ads, "
                    "true quality floored, latency multiplied) is swapped into "
                    "the pool and the router's cached layer list right before "
                    "this query is routed; no router state is touched"
                ),
            },
            "note": (
                "one shared query stream; per seed every method runs it with a "
                "fresh generator seeded s and a fresh pool (the event mutates "
                "the pool); baselines are run as two halves around the swap so "
                "greedy-advertised never adapts while the oracle re-picks "
                "instantly"
            ),
        },
        "method_means": method_means(results["per_run"], config["methods"]),
        "pre_post_mean_reward": results["pre_post_mean_reward"],
        "verdict": results["verdict"],
    }
    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    window = config.get("rolling_window", 10)
    contrast_shares = {
        method: results["mean_shares"][method][spec.tool_name]
        for method in config["methods"]
        if method != ROUTER and method in results["mean_shares"]
    }
    plot_kwargs = dict(
        window=window,
        event_query=spec.query,
        share_threshold=spec.share_threshold,
        sabotaged_tool=spec.tool_name,
    )
    title = (
        f"Searchy {config.get('name', 'M6.6')} — traffic share & reward "
        f"around the sabotage (mean over {len(config['seeds'])} seeds)"
    )
    money_plot(
        results["mean_shares"][ROUTER],
        results["share_band"],
        contrast_shares,
        results["mean_rewards"],
        results["reward_band"],
        out_path=config["figure"],
        title=title,
        **plot_kwargs,
    )
    money_gif(
        results["mean_shares"][ROUTER],
        results["share_band"],
        contrast_shares,
        results["mean_rewards"],
        results["reward_band"],
        out_path=config["gif"],
        title=title,
        fps=config.get("gif_fps", 10),
        **plot_kwargs,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m searchy.sabotage <config.yaml>", file=sys.stderr)
        return 2
    config = load_config(args[0])
    results = run_demo(config)
    write_outputs(results)

    verdict = results["verdict"]
    share = verdict["share_clause"]
    recovery = verdict["recovery_clause"]
    n_seeds = len(verdict["per_seed"])
    print(
        f"share clause: below {share['threshold']:.0%} within "
        f"{verdict['window_queries']} queries on {share['n_pass']}/{n_seeds} "
        f"seeds (required {share['required']}) -> "
        f"{'MET' if share['met'] else 'NOT MET'}"
    )
    print(
        f"recovery clause: back to {recovery['fraction']:.0%} of pre-event "
        f"mean (measured from #{verdict['recovery_measured_from_query']}, "
        "once the trailing window is fully post-event) on "
        f"{recovery['n_pass']}/{n_seeds} seeds (required {recovery['required']}) "
        f"-> {'MET' if recovery['met'] else 'NOT MET'} "
        f"[window-start passes, excluded: {recovery['n_pass_incl_window_start']}]"
    )
    for entry in verdict["per_seed"]:
        below = entry["first_below_query"]
        recovered = entry["recovery_query"]
        early = entry["recovery_query_incl_window_start"]
        note = (
            f" (window-start pass at #{early} excluded — damage had not arrived yet)"
            if early is not None and recovered is None
            else ""
        )
        print(
            f"  seed {entry['seed']}: share {entry['pre_event_share']:.2f} "
            f"pre-event -> min {entry['min_share_in_window']:.2f} in window "
            f"({'below at #' + str(below) if below else 'never below'}); "
            f"reward pre {entry['pre_baseline']:+.3f} -> "
            f"{'recovered at #' + str(recovered) if recovered else 'not recovered in window'}"
            f"{note}"
        )
    print(
        f"overall DoD (both clauses on >= {verdict['share_clause']['required']}"
        f"/{n_seeds} seeds): {'MET' if verdict['dod_met'] else 'NOT MET'}"
    )
    print(f"outputs: {config['output_dir']}/, {config['figure']}, {config['gif']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())