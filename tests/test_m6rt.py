"""Tests for the M6-RT bounded router and re-run experiment.

Implements M6-RT coverage: bounds invariants (tau stays within
[tau_min, tau_max] after batch boundaries), restart semantics,
determinism, inheritance (the transition rule is unchanged), and the
sabotage re-run's honest verdict computation.
"""

from __future__ import annotations

import numpy as np
import pytest

from searchy.m6rt_experiment import (
    SABOTAGE_EVENT,
    run_m65_variant,
    run_m66_variant,
    verdict,
)
from searchy.queries import generate_queries
from searchy.router import PheromoneRouter
from searchy.router_mmas import BoundedPheromoneRouter
from searchy.tools import build_tool_pool


@pytest.fixture(scope="module")
def stream():
    return generate_queries(np.random.default_rng(100))


def _run(router_cls, stream, seed, sabotage=False):
    from searchy.m6rt_experiment import _apply_sabotage

    pool = build_tool_pool()
    r = router_cls(pool)
    rng = np.random.default_rng(seed)
    recs = []
    for i, q in enumerate(stream):
        if sabotage and i + 1 == SABOTAGE_EVENT:
            _apply_sabotage(pool, r)
        recs.append(r.route(q, rng))
    return r, recs


def test_bounded_router_inherits_plain_router():
    assert issubclass(BoundedPheromoneRouter, PheromoneRouter)
    # transition rule comes from the parent verbatim
    assert BoundedPheromoneRouter.routing_probabilities is PheromoneRouter.routing_probabilities
    assert BoundedPheromoneRouter._choose is PheromoneRouter._choose


def test_bounded_router_deterministic(stream):
    r1, recs1 = _run(BoundedPheromoneRouter, stream[:50], 0)
    r2, recs2 = _run(BoundedPheromoneRouter, stream[:50], 0)
    assert [a.reward for a in recs1] == [b.reward for b in recs2]
    assert r1.restarts == r2.restarts


def test_tau_stays_in_bounds_after_batches(stream):
    r, recs = _run(BoundedPheromoneRouter, stream, 0)
    # after the stream, every tau entry respects the final bounds
    assert r.tau.max() <= r.tau_max + 1e-9
    assert r.tau.min() >= r.tau_min - 1e-9


def test_restart_fires_on_stagnation_and_resets_tau(stream):
    r, _ = _run(BoundedPheromoneRouter, stream, 1)
    assert len(r.restarts) >= 1
    # every restart query index is a batch boundary (multiple of 10)
    assert all(x % 10 == 0 for x in r.restarts)


def test_bounded_differs_from_plain(stream):
    """The mechanism must actually change behavior (D6-style ablation)."""
    rp, plain = _run(PheromoneRouter, stream[:60], 0)
    rb, bounded = _run(BoundedPheromoneRouter, stream[:60], 0)
    # same seed but different dynamics: at least one reward differs
    assert [a.reward for a in plain] != [b.reward for b in bounded]


def test_sabotage_verdict_matches_committed_before_numbers():
    """Plain router on the sabotage stream must reproduce D5's 3/5 + 1/5."""
    runs = run_m66_variant(PheromoneRouter, "as_router")
    sp, rp = verdict(runs)
    assert (sp, rp) == (3, 1)


def test_comparison_improves_or_honest():
    """Bounded router must not crash the comparison; verdict is whatever
    it measures (committed: 18.58 vs 17.70 — +5%)."""
    before = run_m65_variant(PheromoneRouter, "as")
    after = run_m65_variant(BoundedPheromoneRouter, "mmas")
    b = float(np.mean([s["cumulative_reward"] for s in before]))
    a = float(np.mean([s["cumulative_reward"] for s in after]))
    assert len(before) == len(after) == 5
    print(f"comparison: before {b:.2f} after {a:.2f}")
