"""Tests for the Firecrawl overlay experiment (FO.2).

Implements FO.2 test coverage: world built only from recorded evidence,
reward-scale invariants (quality dominates after D9), router determinism,
baseline determinism, and the fixture-store integration. No live calls
anywhere — the fixture file committed with the repo is the world.
"""

from __future__ import annotations

import numpy as np
import pytest

from searchy.firecrawl import FixtureStore
from searchy.fo_experiment import (
    COST_SCALE,
    FIXTURE,
    build_world,
    effective_cost,
    reward,
    run_baselines,
    run_overlay,
)

store = FixtureStore(FIXTURE)
world = build_world(store)


def test_fixture_recorded_and_complete():
    # FO.1's record: 76 calls (25 search + 1 map + 50 scrape), 72 credits.
    assert store.total_calls() == 76
    assert store.total_credits() == 72.0
    assert len(world) == 25


def test_world_qualities_come_from_recorded_evidence():
    # markdown quality 1.0 on every query with a successful recording;
    # json quality 0 exactly where the recorded call failed/timed out
    json_failed = [i for i, w in enumerate(world)
                   if w["process"]["json"]["quality"] == 0.0]
    assert json_failed == [0, 2, 9, 12, 14]  # the recorded timeouts (0-based)
    md_ok = [i for i, w in enumerate(world)
             if w["process"]["markdown"]["quality"] == 1.0]
    assert len(md_ok) >= 23  # at most 2 recorded markdown failures


def test_reward_scale_quality_dominates():
    # D9 regression: a typical scrape must net POSITIVE reward (quality
    # > cost/50), otherwise the deposit clip zeroes all learning.
    for w in world:
        md = w["process"]["markdown"]
        if md["quality"] == 1.0:
            assert reward(md) > 0.5
    # and a timeout json is clearly negative
    bad = world[0]["process"]["json"]
    assert reward(bad) < -0.2


def test_effective_cost_is_unscaled_product_metric():
    w = world[0]
    ro = w["retrieve"]["/search"]
    assert effective_cost(ro) == ro["credits"] + ro["latency_ms"] / 7700.0


def test_run_overlay_deterministic():
    a = run_overlay(7, world)
    b = run_overlay(7, world)
    assert a["total_credits"] == b["total_credits"]
    assert a["total_reward"] == b["total_reward"]
    assert [t["retrieve"] for t in a["trace"]] == [t["retrieve"] for t in b["trace"]]


def test_run_overlay_learns_off_markdown():
    # mean over seeds: markdown share in the last 10 queries must exceed
    # 0.55 (the colony tilts away from json after the recorded timeouts)
    shares = []
    for s in range(10):
        run = run_overlay(s, world)
        picks = [t["process"] for t in run["trace"][-10:]]
        shares.append(picks.count("markdown") / 10.0)
    assert np.mean(shares) > 0.55


def test_baselines_shape():
    b = run_baselines(world, n_seeds=5)
    assert set(b) == {"always-search-markdown", "always-map-json", "random"}
    assert len(b["random"]["per_seed_effective_cost"]) == 5
    # deterministic policies: same effective cost on repeated runs
    b2 = run_baselines(world, n_seeds=5)
    assert b["always-search-markdown"] == b2["always-search-markdown"]


def test_always_map_json_is_the_expensive_default():
    b = run_baselines(world, n_seeds=3)
    assert b["always-map-json"]["effective_cost"] > b["always-search-markdown"]["effective_cost"]
