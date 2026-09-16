"""Tests for the path reward.

Implements M6.3 invariants, including the D1 regression: with the
committed tool magnitudes the reward-best path per query type must be
clearly positive (quality dominates the cost penalty).
"""

import numpy as np

from searchy.queries import QueryType
from searchy.reward import path_penalty, path_reward
from searchy.tools import (
    LAYER_PROCESS,
    LAYER_RETRIEVE,
    ToolResult,
    build_tool_pool,
    tools_in_layer,
)


def _res(quality: float, tokens: int, ms: int) -> ToolResult:
    return ToolResult(quality=quality, cost_tokens=tokens, latency_ms=ms)


def test_reward_hand_computed() -> None:
    # qualities .5 * .4 = .20 ; penalty (100+200)/1e4 + (10+20)/1e3 = .06
    results = [_res(0.5, 100, 10), _res(0.4, 200, 20)]
    assert abs(path_reward(results) - 0.14) < 1e-12


def test_penalty_matches_charter_formula() -> None:
    results = [_res(0.5, 500, 60), _res(0.4, 1000, 90)]
    assert abs(path_penalty(results) - 0.30) < 1e-12


def test_reward_can_be_negative() -> None:
    results = [_res(0.0, 1000, 100), _res(0.0, 1000, 100)]
    assert path_reward(results) < 0


def test_lambda_scales_penalty_only() -> None:
    results = [_res(0.5, 100, 10), _res(0.4, 200, 20)]
    base = path_reward(results)
    doubled = path_reward(results, lam=2.0)
    assert abs(doubled - base + 0.06) < 1e-12  # penalty 0.06 subtracted twice


def test_best_expected_reward_positive_for_every_type() -> None:
    """D1 regression: quality must dominate cost for every query type.

    Uses true quality profiles (expected reward, no call noise). Best
    path per type: factual +0.27, math +0.30, summarization +0.49,
    code +0.41 — all well above 0.2. The worst path anywhere must also
    stay mildly negative, not catastrophically so.
    """
    pool = build_tool_pool()
    all_rewards: list[float] = []
    for qtype in QueryType:
        rewards = [
            path_reward(
                [
                    ToolResult(
                        quality=r.expected_quality(qtype),
                        cost_tokens=r.cost_tokens,
                        latency_ms=r.latency_ms,
                    ),
                    ToolResult(
                        quality=p.expected_quality(qtype),
                        cost_tokens=p.cost_tokens,
                        latency_ms=p.latency_ms,
                    ),
                ]
            )
            for r in tools_in_layer(pool, LAYER_RETRIEVE)
            for p in tools_in_layer(pool, LAYER_PROCESS)
        ]
        assert max(rewards) > 0.2, f"{qtype}: best reward too small — D1 relapse?"
        all_rewards.extend(rewards)
    assert min(all_rewards) > -0.20  # worst path (web_search+small_llm on math ≈ -0.16): mildly negative