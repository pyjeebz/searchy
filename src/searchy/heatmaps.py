"""Runner for the pheromone-heatmap experiment (M6.7).

ROADMAP M6.7: "tau heatmaps per layer at queries 25 / 50 / 75 / 100, split
by query type; math queries visibly route differently from factual queries.
Save PNGs."

Design ruling R3: there is ONE shared 2x3 tau matrix, so raw pheromone
cannot be split by query type — the type structure enters through eta, the
advertised skill. The heatmaps therefore show, per layer and query type,
the EFFECTIVE routing probabilities (tau^alpha * eta^beta — exactly the
router's transition rule) at each snapshot, alongside the realized per-type
traffic shares; the raw tau snapshots are kept in the CSVs and JSON so
nothing is hidden.

Protocol — purely descriptive, zero tuning (see the diagnosis log, D3/D5):

- the same shared query stream (``query_seed``) and router parameters as
  M6.5/M6.6, verbatim from the config; plain stream, no sabotage event;
- snapshot timing: tau right after the snapshot-th query (its deposit and
  any batch evaporation already applied), read off RouteRecord.tau_after;
- effective probabilities are never re-implemented here: each snapshot's
  tau is loaded into a fresh router and read back through the router's own
  ``routing_probabilities``, so the transition rule lives in one place
  (router.py);
- traffic shares are realized picks: the cumulative share of each tool
  among the first N queries of a type (undefined while a type has not yet
  appeared in the stream — masked in the figures);
- figures use the across-seed mean; every per-seed number is in the CSVs.

The DoD clause is qualitative ("visibly"), so no pass/fail verdict is
manufactured. The summary instead reports the quantitative companion: per
snapshot and layer, the argmax tool per query type and the total-variation
distance between the math and factual probability vectors. If math and
factual end up routing identically, that is a finding for the diagnosis
log, not a tuning problem.

CLI::

    uv run python -m searchy.heatmaps experiments/configs/m6.7-heatmaps.yaml
"""

from __future__ import annotations

import json
import sys
import warnings
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
import yaml

from searchy.experiment import record_rows
from searchy.queries import QueryType, generate_queries
from searchy.router import PheromoneRouter
from searchy.tools import (
    LAYER_PROCESS,
    LAYER_RETRIEVE,
    build_tool_pool,
    tools_in_layer,
)
from searchy.viz import heatmap_panels

ROUTER = "pheromone_router"

LAYER_NAMES: dict[int, str] = {LAYER_RETRIEVE: "retrieve", LAYER_PROCESS: "process"}
_LAYERS: tuple[int, ...] = (LAYER_RETRIEVE, LAYER_PROCESS)

_REQUIRED_KEYS = (
    "n_per_type",
    "query_seed",
    "seeds",
    "snapshot_queries",
    "router",
    "output_dir",
    "figure_retrieve",
    "figure_process",
    "figure_shares_retrieve",
    "figure_shares_process",
    "figure_tau",
)


def load_config(path: str) -> dict[str, Any]:
    """Load and validate an experiment YAML config."""
    with open(path) as f:
        config: dict[str, Any] = yaml.safe_load(f)
    missing = [key for key in _REQUIRED_KEYS if key not in config]
    if missing:
        raise ValueError(f"config {path} is missing required keys: {missing}")
    return config


def validate_run(config: dict[str, Any]) -> list[int]:
    """Check the snapshot plan against the stream length; return snapshots.

    Snapshots are 1-based query indices, must be unique and increasing, and
    must land inside the stream (1 <= N <= 4 * n_per_type): a snapshot past
    the last query has no ``tau_after`` to read.
    """
    n_queries = 4 * config["n_per_type"]
    if not config["seeds"]:
        raise ValueError("seeds must not be empty")
    snapshots = list(config["snapshot_queries"])
    if not snapshots:
        raise ValueError("snapshot_queries must not be empty")
    if len(set(snapshots)) != len(snapshots):
        raise ValueError("snapshot_queries must not repeat a query index")
    if snapshots != sorted(snapshots):
        raise ValueError("snapshot_queries must be in increasing order")
    out_of_range = [snapshot for snapshot in snapshots if not 1 <= snapshot <= n_queries]
    if out_of_range:
        raise ValueError(
            f"the stream has {n_queries} queries; snapshots {out_of_range} are out of range"
        )
    return snapshots


def snapshot_tau(records: Sequence[Any], snapshot: int) -> np.ndarray:
    """The pheromone matrix right after the ``snapshot``-th query.

    ``records`` is 0-indexed, snapshots are 1-based: tau after query N is
    ``records[N - 1].tau_after`` — the deposit of that query and any batch
    evaporation are already applied. Returns a copy.
    """
    return np.asarray(records[snapshot - 1].tau_after, dtype=float).copy()


def effective_probabilities(
    tau: np.ndarray, pool: dict, router_params: dict[str, Any]
) -> np.ndarray:
    """Effective P(tool | layer, type) at a tau snapshot — shape (2, 4, 3).

    R3: tau is one shared matrix, so the per-type split comes from eta. A
    fresh router is seeded with the snapshot tau and read back through its
    own ``routing_probabilities``, so the transition rule is used, never
    re-implemented.
    """
    router = PheromoneRouter(pool, **router_params)
    router.tau = np.asarray(tau, dtype=float)
    return np.array(
        [
            [router.routing_probabilities(layer, qtype) for qtype in QueryType]
            for layer in _LAYERS
        ],
        dtype=float,
    )


def traffic_shares(
    records: Sequence[Any], snapshot: int, layer: int, tool_names: Sequence[str]
) -> tuple[np.ndarray, np.ndarray]:
    """Realized per-type traffic shares among the first ``snapshot`` queries.

    The picks, not the probabilities: for each query type, the cumulative
    share of each Layer-``layer`` tool. A type with no queries yet in the
    prefix has an undefined share (NaN) — it is masked in the figures and
    excluded from means. Returns (shares (4, 3), counts (4,)).
    """
    shares = np.full((len(QueryType), len(tool_names)), np.nan)
    counts = np.zeros(len(QueryType), dtype=int)
    picks_by_type: dict[QueryType, Counter] = {}
    for record in records[:snapshot]:
        picks = picks_by_type.setdefault(record.query.qtype, Counter())
        picks[record.path[layer]] += 1
    for index, qtype in enumerate(QueryType):
        picks = picks_by_type.get(qtype)
        counts[index] = sum(picks.values()) if picks else 0
        if counts[index]:
            shares[index] = [picks.get(name, 0) / counts[index] for name in tool_names]
    return shares, counts


def _nan_mean(stack: Sequence[np.ndarray]) -> np.ndarray:
    """Across-seed mean of share matrices, ignoring undefined (NaN) cells.

    A type missing from one seed's prefix must not poison the cell; a type
    missing from every seed's prefix stays NaN.
    """
    data = np.stack(stack)
    defined = (~np.isnan(data)).sum(axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # all-NaN slices
        mean = np.nanmean(data, axis=0)
    return np.where(defined > 0, mean, np.nan)


def type_separation(
    mean_probs: dict[int, np.ndarray],
    mean_shares: dict[int, dict[int, np.ndarray]],
    tool_names: dict[int, list[str]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Quantitative companion to the qualitative DoD clause.

    Per snapshot and layer: which tool each type's probability vector points
    at, and how far math sits from factual (total-variation distance, in
    [0, 1]) — for effective probabilities and for realized shares. Reported
    whatever it turns out to be; a zero distance is a finding, not a bug.
    """
    types = list(QueryType)
    factual = types.index(QueryType.FACTUAL)
    math = types.index(QueryType.MATH)
    separation: dict[str, dict[str, dict[str, Any]]] = {}
    for snapshot, probs in mean_probs.items():
        by_layer: dict[str, dict[str, Any]] = {}
        for layer, names in tool_names.items():
            prob_factual = probs[layer][factual]
            prob_math = probs[layer][math]
            share_factual = mean_shares[snapshot][layer][factual]
            share_math = mean_shares[snapshot][layer][math]
            share_distance = None
            if not (np.isnan(share_factual).any() or np.isnan(share_math).any()):
                share_distance = 0.5 * float(np.abs(share_math - share_factual).sum())
            by_layer[LAYER_NAMES[layer]] = {
                "argmax_by_type": {
                    qtype.value: names[int(np.argmax(probs[layer][index]))]
                    for index, qtype in enumerate(types)
                },
                "tv_probabilities": 0.5 * float(np.abs(prob_math - prob_factual).sum()),
                "tv_shares": share_distance,
            }
        separation[str(snapshot)] = by_layer
    return separation


def run_experiment(config: dict[str, Any]) -> dict[str, Any]:
    """Run every seed over the shared stream and aggregate the snapshots.

    Deterministic given the config: same config in, same numbers out.
    """
    snapshots = validate_run(config)
    pool = build_tool_pool()
    stream_rng = np.random.default_rng(config["query_seed"])
    queries = generate_queries(stream_rng, n_per_type=config["n_per_type"])
    router_params = dict(config["router"])
    tool_names = {
        layer: [tool.name for tool in tools_in_layer(pool, layer)] for layer in _LAYERS
    }
    type_values = [qtype.value for qtype in QueryType]
    type_enums = list(QueryType)

    rows: list[dict[str, Any]] = []
    snapshot_rows: list[dict[str, Any]] = []
    per_seed_tau: dict[int, dict[str, dict[str, list[float]]]] = {}
    probs_stack: dict[int, list[np.ndarray]] = {snapshot: [] for snapshot in snapshots}
    shares_stack: dict[int, dict[int, list[np.ndarray]]] = {
        snapshot: {layer: [] for layer in _LAYERS} for snapshot in snapshots
    }
    tau_stack: dict[int, list[np.ndarray]] = {snapshot: [] for snapshot in snapshots}

    for seed in config["seeds"]:
        rng = np.random.default_rng(seed)
        router = PheromoneRouter(pool, **router_params)
        records = router.route_stream(queries, rng)
        rows.extend(record_rows(ROUTER, seed, records))
        seed_tau: dict[str, dict[str, list[float]]] = {}
        for snapshot in snapshots:
            tau = snapshot_tau(records, snapshot)
            seed_tau[str(snapshot)] = {
                LAYER_NAMES[layer]: [float(value) for value in tau[layer]]
                for layer in _LAYERS
            }
            tau_stack[snapshot].append(tau)
            probs = effective_probabilities(tau, pool, router_params)
            probs_stack[snapshot].append(probs)
            for layer in _LAYERS:
                shares, counts = traffic_shares(records, snapshot, layer, tool_names[layer])
                shares_stack[snapshot][layer].append(shares)
                for type_index, (type_value, share_row) in enumerate(
                    zip(type_values, shares)
                ):
                    for tool_index, tool_name in enumerate(tool_names[layer]):
                        snapshot_rows.append(
                            {
                                "seed": seed,
                                "snapshot_query": snapshot,
                                "layer": LAYER_NAMES[layer],
                                "query_type": type_value,
                                "tool": tool_name,
                                "tau": float(tau[layer, tool_index]),
                                "eta": float(
                                    pool[tool_name].advertised[type_enums[type_index]]
                                ),
                                "effective_probability": float(
                                    probs[layer, type_index, tool_index]
                                ),
                                "traffic_share": (
                                    None
                                    if np.isnan(share_row[tool_index])
                                    else float(share_row[tool_index])
                                ),
                                "n_type_queries_in_prefix": int(counts[type_index]),
                            }
                        )
        per_seed_tau[seed] = seed_tau

    mean_probs = {snapshot: np.mean(stack, axis=0) for snapshot, stack in probs_stack.items()}
    mean_shares = {
        snapshot: {layer: _nan_mean(stack) for layer, stack in by_layer.items()}
        for snapshot, by_layer in shares_stack.items()
    }
    mean_tau = {snapshot: np.mean(stack, axis=0) for snapshot, stack in tau_stack.items()}
    separation = type_separation(mean_probs, mean_shares, tool_names)
    return {
        "config": config,
        "rows": rows,
        "snapshot_rows": snapshot_rows,
        "tool_names": tool_names,
        "mean_probs": mean_probs,
        "mean_shares": mean_shares,
        "mean_tau": mean_tau,
        "per_seed_tau": per_seed_tau,
        "separation": separation,
    }


def write_outputs(results: dict[str, Any]) -> None:
    """Write records CSV, snapshot audit CSV, summary JSON, and the five
    figures. Paths come from the config (cwd-relative)."""
    config = results["config"]
    out_dir = Path(config["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results["rows"]).to_csv(out_dir / "records.csv", index=False)
    pd.DataFrame(results["snapshot_rows"]).to_csv(out_dir / "snapshots.csv", index=False)

    snapshots = list(config["snapshot_queries"])
    tool_names = results["tool_names"]
    type_values = [qtype.value for qtype in QueryType]
    n_seeds = len(config["seeds"])

    def probability_grid() -> dict[str, Any]:
        return {
            str(snapshot): {
                LAYER_NAMES[layer]: {
                    type_value: {
                        name: float(results["mean_probs"][snapshot][layer, type_index, tool_index])
                        for tool_index, name in enumerate(tool_names[layer])
                    }
                    for type_index, type_value in enumerate(type_values)
                }
                for layer in _LAYERS
            }
            for snapshot in snapshots
        }

    def share_grid() -> dict[str, Any]:
        grid: dict[str, Any] = {}
        for snapshot in snapshots:
            by_layer: dict[str, Any] = {}
            for layer in _LAYERS:
                matrix = results["mean_shares"][snapshot][layer]
                by_layer[LAYER_NAMES[layer]] = {
                    type_value: {
                        name: (
                            None
                            if np.isnan(matrix[type_index, tool_index])
                            else float(matrix[type_index, tool_index])
                        )
                        for tool_index, name in enumerate(tool_names[layer])
                    }
                    for type_index, type_value in enumerate(type_values)
                }
            grid[str(snapshot)] = by_layer
        return grid

    summary = {
        "protocol": {
            "n_queries": 4 * config["n_per_type"],
            "query_seed": config["query_seed"],
            "seeds": config["seeds"],
            "snapshot_queries": snapshots,
            "router_params": config["router"],
            "note": (
                "descriptive, zero tuning: the same shared query stream and "
                "router parameters as M6.5/M6.6, verbatim; a snapshot is tau "
                "right after that query (deposit and any batch evaporation "
                "applied); R3 — tau is one shared matrix, so the per-type "
                "split in the figures comes from eta via the effective "
                "routing probabilities (tau^alpha * eta^beta), shown next to "
                "the realized per-type traffic shares"
            ),
        },
        "mean_effective_probabilities": probability_grid(),
        "mean_traffic_shares": share_grid(),
        "mean_tau": {
            str(snapshot): {
                LAYER_NAMES[layer]: [float(value) for value in results["mean_tau"][snapshot][layer]]
                for layer in _LAYERS
            }
            for snapshot in snapshots
        },
        "type_separation": results["separation"],
        "per_seed_tau": results["per_seed_tau"],
    }
    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    snapshot_labels = [f"after query #{snapshot}" for snapshot in snapshots]
    for layer in _LAYERS:
        layer_name = LAYER_NAMES[layer]
        heatmap_panels(
            [
                (label, results["mean_probs"][snapshot][layer])
                for snapshot, label in zip(snapshots, snapshot_labels)
            ],
            row_labels=type_values,
            col_labels=tool_names[layer],
            out_path=config[f"figure_{layer_name}"],
            title=(
                f"Searchy {config.get('name', 'M6.7')} — effective routing "
                f"probabilities, {layer_name} layer (mean over {n_seeds} seeds)"
            ),
            value_label="effective routing probability",
            vmin=0.0,
            vmax=1.0,
        )
        heatmap_panels(
            [
                (label, results["mean_shares"][snapshot][layer])
                for snapshot, label in zip(snapshots, snapshot_labels)
            ],
            row_labels=type_values,
            col_labels=tool_names[layer],
            out_path=config[f"figure_shares_{layer_name}"],
            title=(
                f"Searchy {config.get('name', 'M6.7')} — realized per-type "
                f"traffic shares, {layer_name} layer (mean over {n_seeds} seeds)"
            ),
            value_label="cumulative traffic share",
            vmin=0.0,
            vmax=1.0,
        )

    tau_panels = {
        layer: np.array([results["mean_tau"][snapshot][layer] for snapshot in snapshots]).T
        for layer in _LAYERS
    }
    heatmap_panels(
        [(LAYER_NAMES[layer], tau_panels[layer]) for layer in _LAYERS],
        row_labels=tool_names[LAYER_RETRIEVE],
        col_labels=[f"#{snapshot}" for snapshot in snapshots],
        out_path=config["figure_tau"],
        title=(
            f"Searchy {config.get('name', 'M6.7')} — raw pheromone tau "
            f"(mean over {n_seeds} seeds)"
        ),
        value_label="tau",
        ncols=2,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m searchy.heatmaps <config.yaml>", file=sys.stderr)
        return 2
    config = load_config(args[0])
    results = run_experiment(config)
    write_outputs(results)

    snapshots = list(config["snapshot_queries"])
    type_values = [qtype.value for qtype in QueryType]
    separation = results["separation"]
    print(
        f"pheromone heatmaps written (mean over {len(config['seeds'])} seeds; "
        "per-seed numbers are in the CSVs)"
    )
    print(
        "type separation, math vs factual (total-variation distance in [0, 1], "
        "effective probabilities / realized shares):"
    )
    for layer in _LAYERS:
        layer_name = LAYER_NAMES[layer]
        trajectory = []
        for snapshot in snapshots:
            entry = separation[str(snapshot)][layer_name]
            shares_text = "—" if entry["tv_shares"] is None else f"{entry['tv_shares']:.2f}"
            trajectory.append(f"#{snapshot}: {entry['tv_probabilities']:.2f} / {shares_text}")
        print(f"  {layer_name:>8}: " + " | ".join(trajectory))
    print("final-snapshot argmax per type (effective probabilities):")
    final = separation[str(snapshots[-1])]
    for layer in _LAYERS:
        layer_name = LAYER_NAMES[layer]
        picks = final[layer_name]["argmax_by_type"]
        print(f"  {layer_name:>8}: " + ", ".join(f"{t} -> {picks[t]}" for t in type_values))
    print(f"outputs: {config['output_dir']}/ and figures under {Path(config['figure_tau']).parent}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())