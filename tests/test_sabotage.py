"""Tests for the sabotage-adaptation demo runner and its DoD verdict.

Implements M6.6 invariants:

- the event is a pure environment change: truth changes, ads do not, and
  the router's learning state (tau, probabilities) is untouched;
- greedy-advertised never adapts (same paths before and after the event)
  while the oracle re-picks from the sabotaged profiles;
- the share clause is strict (exactly at the threshold does not pass);
- recovery is only credited once the trailing rolling window is fully
  post-event — the D5 window-start artifact — and window-start passes are
  counted separately, never silently dropped;
- the demo is deterministic and all methods share one query stream.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from searchy.queries import Query, QueryType, generate_queries
from searchy.router import PheromoneRouter
from searchy.sabotage import (
    ROUTER,
    SabotageSpec,
    apply_sabotage,
    compute_verdict,
    load_config,
    main,
    make_sabotaged_tool,
    retrieve_share,
    run_baseline_with_event,
    run_demo,
    run_router_with_event,
    spec_from_config,
    write_outputs,
)
from searchy.tools import LAYER_RETRIEVE, build_tool_pool


def _spec(**overrides: Any) -> SabotageSpec:
    values: dict[str, Any] = {
        "tool_name": "web_search",
        "query": 10,  # 1-based -> event_index 9
        "quality": 0.05,
        "latency_multiplier": 3,
        "adaptation_window": 5,
        "share_threshold": 0.2,
        "recovery_fraction": 0.9,
    }
    values.update(overrides)
    return SabotageSpec(**values)


def _small_config(tmp_path) -> dict[str, Any]:
    return {
        "name": "test-sabotage",
        "n_per_type": 5,  # 4 x 5 = 20 queries per run
        "query_seed": 100,
        "seeds": [0, 1],
        "methods": [ROUTER, "greedy-advertised", "oracle"],
        "router": {
            "alpha": 1.0,
            "beta": 2.0,
            "rho": 0.05,
            "epsilon": 0.1,
            "q": 1.0,
            "tau0": 1.0,
            "evaporation_batch": 10,
        },
        "rolling_window": 4,
        "sabotage": {
            "tool": "web_search",
            "query": 10,
            "quality": 0.05,
            "latency_multiplier": 3,
            "adaptation_window": 5,
            "share_threshold": 0.2,
            "recovery_fraction": 0.9,
        },
        "output_dir": str(tmp_path / "out"),
        "figure": str(tmp_path / "fig" / "sabotage.png"),
        "gif": str(tmp_path / "fig" / "sabotage.gif"),
        "gif_fps": 4,
    }


# Verdict inputs are hand-computed so the clause arithmetic is pinned.
# With the _spec defaults (event_index 9, adaptation_window 5) and window 3:
# post = indices 9..13, pre = 4..8, sustained = 11..13.
_SHARE_PASS = [0.5] * 12 + [0.1] * 8  # first strictly below 0.2 at query #13
_REWARDS_RECOVER = [0.2] * 9 + [0.0] + [0.2] * 10  # sustained rolling hits 0.2 >= 0.18 at #13
_REWARDS_STUCK = [0.2] * 9 + [0.05] * 11  # sustained rolling 0.05 < 0.18 forever
_REWARDS_D5 = [0.2] * 11 + [-1.0] * 9  # nominal pass at #10, damage lands right after


def _seed_entry(seed: int, share: list[float], rewards: list[float]) -> dict[str, Any]:
    return {"seed": seed, "share": share, "rewards": rewards}


def test_make_sabotaged_tool_changes_truth_not_ads() -> None:
    tool = build_tool_pool()["web_search"]
    sabotaged = make_sabotaged_tool(tool, _spec())
    assert sabotaged is not tool
    assert all(q == 0.05 for q in sabotaged.true_quality.values())
    assert sabotaged.latency_ms == tool.latency_ms * 3
    assert sabotaged.name == tool.name
    assert sabotaged.layer == tool.layer
    assert sabotaged.cost_tokens == tool.cost_tokens
    assert sabotaged.advertised == tool.advertised
    # the original tool is untouched (frozen dataclass, replace returns new)
    assert tool.latency_ms == 60
    assert tool.true_quality[QueryType.FACTUAL] == 0.95


def test_apply_sabotage_swaps_pool_and_router_layers() -> None:
    pool = build_tool_pool()
    router = PheromoneRouter(pool)
    spec = _spec()
    tau_before = router.tau.copy()
    probs_before = router.routing_probabilities(LAYER_RETRIEVE, QueryType.FACTUAL)

    replacement = apply_sabotage(pool, router, spec)

    assert pool[spec.tool_name] is replacement
    assert any(tool is replacement for tool in router.layers[LAYER_RETRIEVE])
    assert np.array_equal(router.tau, tau_before)
    probs_after = router.routing_probabilities(LAYER_RETRIEVE, QueryType.FACTUAL)
    np.testing.assert_allclose(probs_after, probs_before)


def test_apply_sabotage_rejects_unknown_tool() -> None:
    with pytest.raises(ValueError, match="not in the pool"):
        apply_sabotage(build_tool_pool(), PheromoneRouter(build_tool_pool()), _spec(tool_name="nope"))


def test_retrieve_share_is_a_rolling_indicator() -> None:
    paths = ["web_search", "knowledge_base", "web_search", "web_search", "vector_db"]
    records = [SimpleNamespace(path=(name, "anything")) for name in paths]
    share = retrieve_share(records, "web_search", window=3)
    np.testing.assert_allclose(share, [1.0, 0.5, 2.0 / 3.0, 2.0 / 3.0, 2.0 / 3.0])


def test_verdict_passes_when_both_clauses_hold() -> None:
    verdict = compute_verdict([_seed_entry(0, _SHARE_PASS, _REWARDS_RECOVER)], _spec(), window=3)
    assert verdict["share_clause"]["met"]
    assert verdict["recovery_clause"]["met"]
    assert verdict["dod_met"]
    entry = verdict["per_seed"][0]
    assert entry["share_pass"]
    assert entry["first_below_query"] == 13
    assert entry["recovery_pass"]
    assert entry["recovery_query"] == 13
    assert entry["recovery_query_incl_window_start"] == 13
    assert entry["recovery_target"] == pytest.approx(0.18)
    assert entry["min_rolling_reward_in_window"] == pytest.approx(0.13333, abs=1e-3)
    assert verdict["recovery_measured_from_query"] == 12


def test_verdict_fails_when_recovery_never_reaches_target() -> None:
    verdict = compute_verdict([_seed_entry(0, _SHARE_PASS, _REWARDS_STUCK)], _spec(), window=3)
    assert verdict["share_clause"]["met"]
    assert not verdict["recovery_clause"]["met"]
    assert not verdict["dod_met"]
    entry = verdict["per_seed"][0]
    assert entry["recovery_query"] is None
    assert entry["recovery_query_incl_window_start"] is None
    assert entry["passes_both"] is False


def test_window_start_pass_excluded_before_damage_arrives() -> None:
    # D5: a nominal recovery "pass" at query #10 still averages mostly
    # pre-event rewards — the trailing window has not absorbed any damage
    # yet. The sustained check must not credit it; the early pass stays
    # visible as n_pass_incl_window_start.
    verdict = compute_verdict([_seed_entry(0, _SHARE_PASS, _REWARDS_D5)], _spec(), window=3)
    entry = verdict["per_seed"][0]
    assert not entry["recovery_pass"]
    assert entry["recovery_query"] is None
    assert entry["recovery_query_incl_window_start"] == 10
    assert verdict["recovery_clause"]["n_pass"] == 0
    assert verdict["recovery_clause"]["n_pass_incl_window_start"] == 1
    assert not verdict["dod_met"]


def test_share_threshold_is_strict() -> None:
    verdict = compute_verdict([_seed_entry(0, [0.2] * 20, _REWARDS_RECOVER)], _spec(), window=3)
    entry = verdict["per_seed"][0]
    assert not entry["share_pass"]
    assert entry["first_below_query"] is None
    assert not verdict["share_clause"]["met"]


def test_recovery_target_is_inclusive() -> None:
    spec = replace(_spec(), recovery_fraction=1.0)
    verdict = compute_verdict([_seed_entry(0, _SHARE_PASS, [0.2] * 20)], spec, window=3)
    entry = verdict["per_seed"][0]
    assert entry["recovery_pass"]
    assert entry["recovery_query"] == 12


def test_verdict_counts_clauses_and_conjunction() -> None:
    per_seed = [
        _seed_entry(0, _SHARE_PASS, _REWARDS_RECOVER),
        _seed_entry(1, _SHARE_PASS, _REWARDS_RECOVER),
        _seed_entry(2, _SHARE_PASS, _REWARDS_RECOVER),
        _seed_entry(3, [0.5] * 9 + [0.1] * 11, _REWARDS_STUCK),
        _seed_entry(4, [0.2] * 20, _REWARDS_RECOVER),
    ]
    verdict = compute_verdict(per_seed, _spec(), window=3)
    assert verdict["share_clause"]["n_pass"] == 4
    assert verdict["share_clause"]["required"] == 4
    assert verdict["share_clause"]["met"]
    assert verdict["recovery_clause"]["n_pass"] == 4
    assert verdict["recovery_clause"]["required"] == 4
    assert verdict["recovery_clause"]["met"]
    assert verdict["seeds_passing_both"] == 3
    assert not verdict["dod_met"]


def test_vacuous_share_pass_is_flagged() -> None:
    verdict = compute_verdict([_seed_entry(0, [0.1] * 20, _REWARDS_RECOVER)], _spec(), window=3)
    entry = verdict["per_seed"][0]
    assert entry["share_pass"]  # below the threshold in the window...
    assert entry["share_below_before_event"]  # ...but it already was pre-event


def test_sabotaged_router_records_show_the_event() -> None:
    stream = generate_queries(np.random.default_rng(100), n_per_type=5)
    spec = _spec()
    # alpha = beta = 0 flattens the transition rule to uniform, so picks
    # sample every tool regardless of tau or ads — the timing check is
    # about the environment swap, not the learning rule.
    params = {
        "alpha": 0.0,
        "beta": 0.0,
        "rho": 0.05,
        "epsilon": 0.0,
        "q": 1.0,
        "tau0": 1.0,
        "evaporation_batch": 10,
    }
    event = spec.event_index
    original = build_tool_pool()["web_search"]
    pre_picks: list[Any] = []
    post_picks: list[Any] = []
    for seed in range(4):
        records = run_router_with_event(build_tool_pool(), stream, seed, params, spec)
        for index, record in enumerate(records):
            if record.path[0] == "web_search":
                (pre_picks if index < event else post_picks).append(record)
    assert pre_picks and post_picks  # uniform picks must hit both halves
    # quality is per-type: web_search's true quality varies by query type, so
    # compare against the untouched profile with 3-sigma (0.15) slack for the
    # N(0, 0.05) call noise
    for record in pre_picks:
        assert record.results[0].latency_ms == 60
        expected = original.true_quality[record.query.qtype]
        assert abs(record.results[0].quality - expected) <= 0.15
    for record in post_picks:
        assert record.results[0].latency_ms == 180
        assert 0.0 <= record.results[0].quality <= 0.2


def test_greedy_advertised_never_adapts() -> None:
    # interleaved types so every query has its twin across the event
    stream = [
        Query(QueryType.FACTUAL, f"f{i}") if i % 2 == 0 else Query(QueryType.MATH, f"m{i}")
        for i in range(8)
    ]
    spec = _spec(query=5)
    records = run_baseline_with_event("greedy-advertised", build_tool_pool(), stream, 0, spec)
    for index in range(4):
        assert records[index].path == records[index + 4].path
    # the ads still point at web_search for factual lookups, so the same
    # path is taken straight into the sabotage: slow tool, floored quality
    assert records[0].path[0] == "web_search"
    assert records[0].results[0].latency_ms == 60
    assert records[4].results[0].latency_ms == 180
    assert records[0].results[0].quality >= 0.7
    assert records[4].results[0].quality <= 0.3


def test_oracle_repicks_after_the_event() -> None:
    stream = [Query(QueryType.FACTUAL, f"f{i}") for i in range(8)]
    spec = _spec(query=5)
    records = run_baseline_with_event("oracle", build_tool_pool(), stream, 0, spec)
    assert all(record.path == ("web_search", "small_llm") for record in records[:4])
    assert all(record.path == ("knowledge_base", "small_llm") for record in records[4:])


def test_run_demo_is_deterministic_with_shared_stream(tmp_path) -> None:
    config = _small_config(tmp_path)
    first = run_demo(config)
    second = run_demo(config)
    assert first["rows"] == second["rows"]
    assert first["verdict"] == second["verdict"]
    frame = pd.DataFrame(first["rows"])
    per_query = frame.groupby(["seed", "query_index"])["query_type"].nunique()
    assert (per_query == 1).all()
    counts = frame.groupby(["seed", "method"]).size()
    assert (counts == 20).all()


def test_write_outputs_writes_records_summary_and_money_files(tmp_path) -> None:
    config = _small_config(tmp_path)
    results = run_demo(config)
    write_outputs(results)

    out_dir = Path(config["output_dir"])
    records = pd.read_csv(out_dir / "records.csv")
    assert len(records) == 2 * 3 * 20
    summary_runs = pd.read_csv(out_dir / "summary.csv")
    assert len(summary_runs) == 6

    with open(out_dir / "summary.json") as f:
        summary = json.load(f)
    assert summary["protocol"]["sabotage"]["query"] == 10
    verdict = summary["verdict"]
    assert len(verdict["per_seed"]) == 2
    assert verdict["recovery_measured_from_query"] == 13
    assert "n_pass_incl_window_start" in verdict["recovery_clause"]
    assert isinstance(verdict["dod_met"], bool)
    pre_post = summary["pre_post_mean_reward"]
    assert pre_post["greedy-advertised"]["post_event"] < pre_post["oracle"]["post_event"]

    figure = Path(config["figure"])
    assert figure.exists() and figure.stat().st_size > 0
    with open(config["gif"], "rb") as f:
        assert f.read(4) == b"GIF8"


def test_load_config_requires_keys(tmp_path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("name: bad\n")
    with pytest.raises(ValueError, match="missing required keys"):
        load_config(str(path))


def test_spec_from_config_requires_sabotage_keys(tmp_path) -> None:
    config = _small_config(tmp_path)
    del config["sabotage"]["latency_multiplier"]
    with pytest.raises(ValueError, match="sabotage block is missing required keys"):
        spec_from_config(config)


def test_run_demo_validates_the_dod_windows(tmp_path) -> None:
    config = _small_config(tmp_path)

    # event 12 + window 12 = 24 > 20 queries in the stream (window alone
    # cannot overflow here: 9 + w > 20 needs w > 11, which trips the
    # pre-event check first, so the event is moved back to query #13)
    overflowing = {
        **config,
        "sabotage": {**config["sabotage"], "query": 13, "adaptation_window": 12},
    }
    with pytest.raises(ValueError, match="stream has 20 queries"):
        run_demo(overflowing)

    # event index 4 < 5 pre-event queries needed
    short_pre = {**config, "sabotage": {**config["sabotage"], "query": 5}}
    with pytest.raises(ValueError, match="pre-event queries"):
        run_demo(short_pre)

    no_router = {**config, "methods": ["greedy-advertised", "oracle"]}
    with pytest.raises(ValueError, match="pheromone"):
        run_demo(no_router)

    wide_window = {**config, "rolling_window": 6}
    with pytest.raises(ValueError, match="fully post-event"):
        run_demo(wide_window)

    bad_query = {**config, "sabotage": {**config["sabotage"], "query": 0}}
    with pytest.raises(ValueError, match="must be >= 1"):
        run_demo(bad_query)

    no_seeds = {**config, "seeds": []}
    with pytest.raises(ValueError, match="seeds must not be empty"):
        run_demo(no_seeds)


def test_main_rejects_bad_usage(capsys) -> None:
    assert main([]) == 2
    assert main(["a", "b"]) == 2
    assert "usage" in capsys.readouterr().err