"""Tests for the non-learning baselines.

Implements M6.4 invariants: baseline correctness (each baseline picks by
its own definition), determinism, and — the point of the whole milestone —
the oracle strictly beating greedy-advertised on the misled types (the D2
regression: the misleading ads must give the strawman teeth).
"""

import numpy as np
import pytest

from searchy.baselines import (
    BASELINE_NAMES,
    BaselineRecord,
    expected_path_reward,
    oracle_path,
    penalty_scale,
    run_baseline,
    run_random,
)
from searchy.queries import QueryType, generate_queries
from searchy.reward import path_reward
from searchy.tools import (
    LAYER_PROCESS,
    LAYER_RETRIEVE,
    build_tool_pool,
    tools_in_layer,
)

POOL = build_tool_pool()
RETRIEVE_NAMES = {t.name for t in tools_in_layer(POOL, LAYER_RETRIEVE)}
PROCESS_NAMES = {t.name for t in tools_in_layer(POOL, LAYER_PROCESS)}


def _stream(seed: int = 1):
    return generate_queries(np.random.default_rng(seed))


def test_greedy_cheapest_picks_penalty_minimizing_pair() -> None:
    """vector_db (0.030) edges knowledge_base (0.032); calculator (0.011)
    wins the process layer outright. Type-blind by construction."""
    records = run_baseline(
        "greedy-cheapest", POOL, _stream(), np.random.default_rng(0)
    )
    assert {r.path for r in records} == {("vector_db", "calculator")}
    # structural: the pick argmins the charter penalty scale per layer
    for layer in (LAYER_RETRIEVE, LAYER_PROCESS):
        tools = tools_in_layer(POOL, layer)
        cheapest = min(tools, key=penalty_scale)
        assert penalty_scale(cheapest) <= min(penalty_scale(t) for t in tools)


def test_greedy_advertised_picks_argmax_ad_per_layer() -> None:
    records = run_baseline(
        "greedy-advertised", POOL, _stream(), np.random.default_rng(0)
    )
    for rec in records:
        qtype = rec.query.qtype
        expected_r = max(
            tools_in_layer(POOL, LAYER_RETRIEVE), key=lambda t: t.advertised[qtype]
        )
        expected_p = max(
            tools_in_layer(POOL, LAYER_PROCESS), key=lambda t: t.advertised[qtype]
        )
        assert rec.path == (expected_r.name, expected_p.name)


def test_greedy_advertised_paths_are_pinned() -> None:
    """Regression pin on the committed ads (D2): greedy-advertised follows
    knowledge_base's summarization oversell, and calculator's math
    undersell hands the process layer to small_llm. If AD_NOISE_SEED or
    MISLEADING_ADS ever change, this fails loudly — that change would need
    a diagnosis-log entry, not a silent test edit."""
    records = run_baseline(
        "greedy-advertised", POOL, _stream(), np.random.default_rng(0)
    )
    by_type = {rec.query.qtype: rec.path for rec in records}
    assert by_type == {
        QueryType.FACTUAL: ("web_search", "small_llm"),
        QueryType.MATH: ("vector_db", "small_llm"),
        QueryType.SUMMARIZATION: ("knowledge_base", "small_llm"),
        QueryType.CODE: ("web_search", "small_llm"),
    }


def test_oracle_paths_are_the_true_best() -> None:
    """The D1 reward landscape, pinned: best path per type is factual
    web_search+small_llm, math knowledge_base+calculator, summarization
    vector_db+small_llm, code vector_db+regex_processor."""
    expected = {
        QueryType.FACTUAL: ("web_search", "small_llm"),
        QueryType.MATH: ("knowledge_base", "calculator"),
        QueryType.SUMMARIZATION: ("vector_db", "small_llm"),
        QueryType.CODE: ("vector_db", "regex_processor"),
    }
    for qtype, path in expected.items():
        assert oracle_path(POOL, qtype) == path
    # and run_oracle routes a mixed stream by type accordingly
    records = run_baseline("oracle", POOL, _stream(), np.random.default_rng(0))
    assert {r.query.qtype: r.path for r in records} == expected


def test_oracle_beats_greedy_advertised_in_expectation() -> None:
    """D2 regression: the misleading ads must cost greedy-advertised real
    reward. Equal on factual (same path), strictly behind on the other
    three types."""
    for qtype in QueryType:
        g_retrieve = max(
            tools_in_layer(POOL, LAYER_RETRIEVE), key=lambda t: t.advertised[qtype]
        )
        g_process = max(
            tools_in_layer(POOL, LAYER_PROCESS), key=lambda t: t.advertised[qtype]
        )
        greedy = expected_path_reward(g_retrieve, g_process, qtype)
        o_retrieve, o_process = oracle_path(POOL, qtype)
        best = expected_path_reward(POOL[o_retrieve], POOL[o_process], qtype)
        assert best >= greedy
        if qtype is not QueryType.FACTUAL:
            assert best > greedy + 0.15, f"{qtype}: misleading ads lost their teeth"


def test_random_deterministic_under_seed() -> None:
    queries = _stream()

    def paths(seed: int) -> list[tuple[str, str]]:
        records = run_random(POOL, queries, np.random.default_rng(seed))
        return [r.path for r in records]

    assert paths(42) == paths(42)
    assert paths(43) != paths(42)


def test_random_covers_all_tools() -> None:
    """Uniform picks over 100 queries must touch every tool in both layers."""
    records = run_random(POOL, _stream(), np.random.default_rng(9))
    assert {r.path[0] for r in records} == RETRIEVE_NAMES
    assert {r.path[1] for r in records} == PROCESS_NAMES


def test_all_baselines_produce_well_formed_records() -> None:
    queries = _stream()
    for name in BASELINE_NAMES:
        records = run_baseline(name, POOL, queries, np.random.default_rng(7))
        assert len(records) == len(queries)
        for rec in records:
            assert isinstance(rec, BaselineRecord)
            assert rec.path[0] in RETRIEVE_NAMES
            assert rec.path[1] in PROCESS_NAMES
            assert len(rec.results) == 2
            # reward is the charter formula on the realized results
            assert abs(rec.reward - path_reward(list(rec.results))) < 1e-12
            for result, tool_name in zip(rec.results, rec.path):
                assert 0.0 <= result.quality <= 1.0
                assert result.cost_tokens == POOL[tool_name].cost_tokens
                assert result.latency_ms == POOL[tool_name].latency_ms


def test_greedy_and_oracle_choices_are_history_independent() -> None:
    """No learning: the deterministic baselines pick identical paths under
    any generator — the rng only affects realized qualities, never choices."""
    queries = _stream()
    for name in ("greedy-cheapest", "greedy-advertised", "oracle"):
        paths_a = [r.path for r in run_baseline(name, POOL, queries, np.random.default_rng(0))]
        paths_b = [r.path for r in run_baseline(name, POOL, queries, np.random.default_rng(123))]
        assert paths_a == paths_b, f"{name} changed its choices with rng seed"


def test_run_baseline_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="unknown baseline"):
        run_baseline("greedy-bestest", POOL, _stream(), np.random.default_rng(0))