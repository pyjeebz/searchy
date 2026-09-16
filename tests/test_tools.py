"""Tests for the simulated tool pool.

Implements M6.2 DoD: any tool on any query returns stable
(quality, cost, latency) under a fixed seed.
"""

import numpy as np

from searchy.queries import Query, QueryType
from searchy.tools import (
    AD_MIN,
    AD_NOISE_SIGMA,
    MISLEADING_ADS,
    LAYER_PROCESS,
    LAYER_RETRIEVE,
    Tool,
    build_tool_pool,
    call_tool,
    tools_in_layer,
)

Q = Query(qtype=QueryType.MATH, payload="compute 47*19+3")


def test_pool_has_six_tools_two_layers() -> None:
    pool = build_tool_pool()
    assert len(pool) == 6
    assert len(tools_in_layer(pool, LAYER_RETRIEVE)) == 3
    assert len(tools_in_layer(pool, LAYER_PROCESS)) == 3


def test_pool_is_deterministic() -> None:
    a = build_tool_pool()
    b = build_tool_pool()
    for name in a:
        assert a[name] == b[name]  # identical ads, profiles, costs every build


def test_call_tool_stable_under_seed() -> None:
    pool = build_tool_pool()
    for name, tool in pool.items():
        r1 = call_tool(tool, Q, np.random.default_rng(99))
        r2 = call_tool(tool, Q, np.random.default_rng(99))
        assert r1 == r2, f"{name} not deterministic under seed"
        # noise is real, not constant: different seeds give some variation
        others = {call_tool(tool, Q, np.random.default_rng(s)).quality for s in range(30)}
        assert len(others) > 1, f"{name} noise appears frozen"


def test_call_result_bounds_and_fixed_costs() -> None:
    pool = build_tool_pool()
    for tool in pool.values():
        r = call_tool(tool, Q, np.random.default_rng(5))
        assert 0.0 <= r.quality <= 1.0
        assert r.cost_tokens == tool.cost_tokens > 0
        assert r.latency_ms == tool.latency_ms > 0


def test_quality_noise_stays_close_to_true_profile() -> None:
    """Mean of many seeded calls approximates the true profile."""
    rng = np.random.default_rng(11)
    pool = build_tool_pool()
    tool = pool["web_search"]
    samples = [call_tool(tool, Q, rng).quality for _ in range(400)]
    assert abs(float(np.mean(samples)) - tool.expected_quality(QueryType.MATH)) < 0.02


def test_advertised_within_bounds() -> None:
    pool = build_tool_pool()
    for tool in pool.values():
        for ad in tool.advertised.values():
            assert AD_MIN <= ad <= 1.0


def test_advertised_close_to_true_except_misleading_pairs() -> None:
    """Honest ads within ~4 sigma of true; the two misleading pairs are not."""
    pool = build_tool_pool()
    for tool in pool.values():
        for qtype, true_q in tool.true_quality.items():
            ad = tool.advertised[qtype]
            if (tool.name, qtype) in MISLEADING_ADS:
                # oversell or undersell — either way clearly off from true
                assert abs(ad - true_q) > 0.10, f"misleading ad too weak: {tool.name}/{qtype}"
                assert ad == MISLEADING_ADS[(tool.name, qtype)]
            else:
                assert abs(ad - true_q) <= 4 * AD_NOISE_SIGMA, (
                    f"ad drifted from true: {tool.name}/{qtype} ad={ad:.3f} true={true_q}"
                )


def test_specific_misleading_ads() -> None:
    pool = build_tool_pool()
    kb = pool["knowledge_base"]
    calc = pool["calculator"]
    assert kb.advertised[QueryType.SUMMARIZATION] == 0.90
    assert kb.true_quality[QueryType.SUMMARIZATION] == 0.50
    assert calc.advertised[QueryType.MATH] == 0.30
    assert calc.true_quality[QueryType.MATH] == 0.98


def test_best_true_tool_differs_by_type() -> None:
    """Profile design: argmax true quality differs across query types."""
    pool = build_tool_pool()
    for qtype, expected_best in [
        (QueryType.FACTUAL, "web_search"),
        (QueryType.MATH, "calculator"),
        (QueryType.SUMMARIZATION, "small_llm"),
        (QueryType.CODE, "small_llm"),
    ]:
        best = max(pool.values(), key=lambda t: t.true_quality[qtype])
        assert best.name == expected_best, f"{qtype}: best={best.name}"


def test_good_for_type_is_not_always_cheapest() -> None:
    """Cost/latency create real trade-offs (e.g. small_llm is the expensive
    best tool for summarization)."""
    pool = build_tool_pool()
    assert pool["small_llm"].cost_tokens == max(t.cost_tokens for t in pool.values())
    assert pool["calculator"].cost_tokens == min(t.cost_tokens for t in pool.values())