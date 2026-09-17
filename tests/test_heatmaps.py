"""Invariants for the pheromone-heatmap experiment (M6.7).

Covered here:
- effective probabilities reproduce the router's transition rule exactly
  (tau^alpha * eta^beta, read back through a fresh router's own
  ``routing_probabilities`` — the rule is used, never re-implemented);
- tau snapshots are the recorded tau_after of the right query, and copies
  (mutating a snapshot cannot touch the records);
- traffic shares are realized picks over the prefix, NaN while a type has
  not yet appeared;
- the run is deterministic given the config and every seed sees the same
  shared query stream;
- snapshot rows are complete (2 seeds x 3 snapshots x 2 layers x 4 types
  x 3 tools), effective probabilities sum to 1 per (seed, snapshot, layer,
  type), and the final snapshot's shares are all defined;
- snapshot validation rejects empty/repeated/non-increasing/out-of-range
  plans and empty seeds;
- outputs: records.csv, snapshots.csv, summary.json (protocol + grids +
  type separation) and the five figures all land on disk;
- config loading requires every key; bad CLI usage exits 2.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import yaml

from searchy.experiment import record_rows
from searchy.heatmaps import (
    effective_probabilities,
    load_config,
    main,
    run_experiment,
    snapshot_tau,
    traffic_shares,
    type_separation,
    validate_run,
    write_outputs,
)
from searchy.queries import QueryType, generate_queries
from searchy.router import PheromoneRouter
from searchy.tools import (
    LAYER_PROCESS,
    LAYER_RETRIEVE,
    build_tool_pool,
    tools_in_layer,
)


def _router_params() -> dict:
    return {
        "alpha": 1.0,
        "beta": 2.0,
        "rho": 0.05,
        "epsilon": 0.1,
        "q": 1.0,
        "tau0": 1.0,
        "evaporation_batch": 10,
    }


def _small_config(tmp_path: Path) -> dict:
    """A 12-query, 2-seed config: snapshots 4 / 8 / 12, outputs in tmp."""
    return {
        "name": "m6.7-test",
        "n_per_type": 3,
        "query_seed": 100,
        "seeds": [0, 1],
        "snapshot_queries": [4, 8, 12],
        "router": _router_params(),
        "output_dir": str(tmp_path / "results"),
        "figure_retrieve": str(tmp_path / "figures" / "retrieve.png"),
        "figure_process": str(tmp_path / "figures" / "process.png"),
        "figure_shares_retrieve": str(tmp_path / "figures" / "shares-retrieve.png"),
        "figure_shares_process": str(tmp_path / "figures" / "shares-process.png"),
        "figure_tau": str(tmp_path / "figures" / "tau.png"),
    }


def test_effective_probabilities_match_the_router_rule():
    """Independently recomputed tau^alpha * eta^beta matches the helper.

    R3: tau is one shared matrix, so the per-type structure must come from
    eta — factual and math must not produce identical probability rows.
    """
    pool = build_tool_pool()
    params = _router_params()
    tau = np.array([[2.0, 1.0, 0.5], [1.5, 1.0, 1.0]])
    probs = effective_probabilities(tau, pool, params)
    assert probs.shape == (2, len(QueryType), 3)
    types = list(QueryType)
    for layer in (LAYER_RETRIEVE, LAYER_PROCESS):
        tools = tools_in_layer(pool, layer)
        for type_index, qtype in enumerate(types):
            scores = tau[layer] ** params["alpha"] * np.array(
                [tool.advertised[qtype] ** params["beta"] for tool in tools]
            )
            expected = scores / scores.sum()
            assert np.allclose(probs[layer, type_index], expected)
            assert probs[layer, type_index].sum() == pytest.approx(1.0)
    # eta differs per type, so the effective probabilities must too.
    assert not np.allclose(probs[LAYER_RETRIEVE, 0], probs[LAYER_RETRIEVE, 1])


def test_effective_probabilities_read_the_routers_own_rule():
    """The helper delegates to a fresh router's routing_probabilities."""
    pool = build_tool_pool()
    tau = np.array([[2.0, 1.0, 0.5], [1.5, 1.0, 1.0]])
    probe = PheromoneRouter(pool, **_router_params())
    probe.tau = tau.copy()
    expected = np.array(
        [
            [probe.routing_probabilities(layer, qtype) for qtype in QueryType]
            for layer in (LAYER_RETRIEVE, LAYER_PROCESS)
        ]
    )
    assert np.allclose(effective_probabilities(tau, pool, _router_params()), expected)


def test_snapshot_tau_is_the_records_snapshot():
    """tau after query N is records[N - 1].tau_after, and a copy of it."""
    pool = build_tool_pool()
    queries = generate_queries(np.random.default_rng(100), n_per_type=3)
    router = PheromoneRouter(pool, **_router_params())
    records = router.route_stream(queries, np.random.default_rng(0))
    for snapshot in (1, 5, 12):
        before = records[snapshot - 1].tau_after.copy()
        grabbed = snapshot_tau(records, snapshot)
        assert np.array_equal(grabbed, before)
        grabbed[0] += 100.0  # mutating the snapshot must not touch the record
        assert np.array_equal(records[snapshot - 1].tau_after, before)


def test_traffic_shares_are_realized_picks():
    """Shares are the cumulative picks per type; unseen types are NaN."""
    layer = LAYER_RETRIEVE
    tool_names = ["knowledge_base", "vector_db", "web_search"]

    def record(qtype: QueryType, tool: str) -> SimpleNamespace:
        return SimpleNamespace(query=SimpleNamespace(qtype=qtype), path=(tool, "small_llm"))

    records = [
        record(QueryType.FACTUAL, "knowledge_base"),
        record(QueryType.FACTUAL, "web_search"),
        record(QueryType.FACTUAL, "web_search"),
        record(QueryType.MATH, "web_search"),
    ]
    shares, counts = traffic_shares(records, 4, layer, tool_names)
    assert np.allclose(shares[0], [1 / 3, 0.0, 2 / 3])
    assert np.allclose(shares[1], [0.0, 0.0, 1.0])
    assert np.isnan(shares[2]).all()
    assert np.isnan(shares[3]).all()
    assert counts.tolist() == [3, 1, 0, 0]
    # an empty prefix has no realized traffic at all
    empty_shares, empty_counts = traffic_shares(records, 0, layer, tool_names)
    assert np.isnan(empty_shares).all()
    assert empty_counts.tolist() == [0, 0, 0, 0]


def test_run_experiment_is_deterministic_with_a_shared_stream(tmp_path):
    """Same config in, same numbers out; every seed sees the same stream."""
    first = run_experiment(_small_config(tmp_path))
    second = run_experiment(_small_config(tmp_path))
    assert first["rows"] == second["rows"]
    assert first["snapshot_rows"] == second["snapshot_rows"]
    for snapshot, matrix in first["mean_probs"].items():
        assert np.array_equal(matrix, second["mean_probs"][snapshot])

    rows = pd.DataFrame(first["rows"])
    # one query type per (seed, query): the stream is shared across seeds
    types_per_slot = rows.groupby(["seed", "query_index"])["query_type"].nunique()
    assert (types_per_slot == 1).all()
    # 12 queries per seed (4 types x n_per_type 3)
    assert (rows.groupby("seed").size() == 12).all()


def test_snapshot_rows_are_complete_and_normalized(tmp_path):
    """Snapshot rows cover the full grid and effective probs sum to 1."""
    results = run_experiment(_small_config(tmp_path))
    snapshot_rows = pd.DataFrame(results["snapshot_rows"])
    # 2 seeds x 3 snapshots x 2 layers x 4 types x 3 tools
    assert len(snapshot_rows) == 2 * 3 * 2 * 4 * 3
    totals = snapshot_rows.groupby(["seed", "snapshot_query", "layer", "query_type"])[
        "effective_probability"
    ].sum()
    assert np.allclose(totals, 1.0)
    final = snapshot_rows[snapshot_rows["snapshot_query"] == 12]
    assert final["traffic_share"].notna().all()  # all types seen by query 12
    assert (final["n_type_queries_in_prefix"] == 3).all()


def test_validate_run_rejects_bad_snapshot_plans(tmp_path):
    """Empty/repeated/non-increasing/out-of-range snapshots are errors."""
    base = _small_config(tmp_path)

    def variant(**overrides: object) -> dict:
        config = dict(base)
        config.update(overrides)
        return config

    assert validate_run(base) == [4, 8, 12]
    with pytest.raises(ValueError, match="out of range"):
        run_experiment(variant(snapshot_queries=[0, 4, 8]))
    with pytest.raises(ValueError, match="out of range"):
        run_experiment(variant(snapshot_queries=[4, 8, 13]))  # stream has 12
    with pytest.raises(ValueError, match="not repeat"):
        run_experiment(variant(snapshot_queries=[4, 4, 12]))
    with pytest.raises(ValueError, match="increasing"):
        run_experiment(variant(snapshot_queries=[8, 4, 12]))
    with pytest.raises(ValueError, match="seeds must not be empty"):
        run_experiment(variant(seeds=[]))
    with pytest.raises(ValueError, match="snapshot_queries must not be empty"):
        run_experiment(variant(snapshot_queries=[]))


def test_type_separation_reports_distances_and_argmaxes():
    """TV distances for probabilities and shares, NaN shares reported None."""
    names = {LAYER_RETRIEVE: ["a", "b"], LAYER_PROCESS: ["a", "b"]}
    # QueryType order: factual, math, summarization, code
    probs = {
        10: np.array(
            [
                [[0.9, 0.1], [0.1, 0.9], [0.5, 0.5], [0.5, 0.5]],
                [[0.6, 0.4], [0.6, 0.4], [0.6, 0.4], [0.6, 0.4]],
            ]
        )
    }
    shares = {
        10: {
            LAYER_RETRIEVE: np.array(
                [[0.5, 0.5], [0.0, 1.0], [np.nan, np.nan], [np.nan, np.nan]]
            ),
            LAYER_PROCESS: np.full((4, 2), np.nan),
        }
    }
    separation = type_separation(probs, shares, names)
    entry = separation["10"]["retrieve"]
    assert entry["argmax_by_type"] == {
        QueryType.FACTUAL.value: "a",
        QueryType.MATH.value: "b",
        QueryType.SUMMARIZATION.value: "a",  # tie -> first tool in the layer
        QueryType.CODE.value: "a",
    }
    assert entry["tv_probabilities"] == pytest.approx(0.8)
    assert entry["tv_shares"] == pytest.approx(0.5)
    # all-NaN shares (process layer) are reported as None, not dropped
    assert separation["10"]["process"]["tv_shares"] is None
    assert separation["10"]["process"]["tv_probabilities"] == pytest.approx(0.0)


def test_write_outputs_writes_csvs_json_and_figures(tmp_path):
    """records.csv, snapshots.csv, summary.json and five figures on disk."""
    config = _small_config(tmp_path)
    results = run_experiment(config)
    write_outputs(results)
    out_dir = Path(config["output_dir"])

    records = pd.read_csv(out_dir / "records.csv")
    assert len(records) == 2 * 12  # seeds x queries
    snapshots = pd.read_csv(out_dir / "snapshots.csv")
    assert len(snapshots) == 2 * 3 * 2 * 4 * 3

    summary = json.loads((out_dir / "summary.json").read_text())
    assert summary["protocol"]["snapshot_queries"] == [4, 8, 12]
    assert set(summary["mean_effective_probabilities"]) == {"4", "8", "12"}
    assert set(summary["mean_effective_probabilities"]["12"]) == {"retrieve", "process"}
    factual = summary["mean_effective_probabilities"]["12"]["retrieve"]["factual-lookup"]
    assert sum(factual.values()) == pytest.approx(1.0)
    for snapshot in ("4", "8", "12"):
        tv = summary["type_separation"][snapshot]["retrieve"]["tv_probabilities"]
        assert 0.0 <= tv <= 1.0

    for key in (
        "figure_retrieve",
        "figure_process",
        "figure_shares_retrieve",
        "figure_shares_process",
        "figure_tau",
    ):
        figure = Path(config[key])
        assert figure.exists()
        assert figure.stat().st_size > 0


def test_run_experiment_rows_match_record_rows(tmp_path):
    """The rows written for the run are exactly record_rows' shape."""
    config = _small_config(tmp_path)
    pool = build_tool_pool()
    queries = generate_queries(np.random.default_rng(config["query_seed"]), n_per_type=3)
    router = PheromoneRouter(pool, **config["router"])
    expected = record_rows("pheromone_router", 0, router.route_stream(queries, np.random.default_rng(0)))
    results = run_experiment(config)
    assert results["rows"][:12] == expected


def test_load_config_requires_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"n_per_type": 3}))
    with pytest.raises(ValueError, match="missing required keys"):
        load_config(str(path))


def test_main_rejects_bad_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert main(["a", "b"]) == 2
    assert "usage" in capsys.readouterr().err