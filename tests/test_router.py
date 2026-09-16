"""Tests for the pheromone router.

Implements M6.3 DoD: routes each query through both layers; τ persists and
changes across a 100-query stream; probability rows sum to 1; everything
deterministic under seed.
"""

import numpy as np

from searchy.queries import generate_queries
from searchy.router import PheromoneRouter, RouteRecord, TAU0, deposit_amount
from searchy.tools import LAYER_RETRIEVE, build_tool_pool, tools_in_layer

RETRIEVE_NAMES = {t.name for t in tools_in_layer(build_tool_pool(), LAYER_RETRIEVE)}
PROCESS_NAMES = {t.name for t in tools_in_layer(build_tool_pool(), 1)}


def _router(**kwargs) -> PheromoneRouter:
    return PheromoneRouter(build_tool_pool(), **kwargs)


def test_probability_rows_sum_to_one() -> None:
    router = _router()
    for layer in (0, 1):
        for qtype in list(router.layers[0][0].advertised):
            probs = router.routing_probabilities(layer, qtype)
            assert probs.shape == (3,)
            assert (probs >= 0.0).all()
            assert abs(probs.sum() - 1.0) < 1e-9


def test_initial_probabilities_follow_advertised_skills() -> None:
    """At uniform tau the transition rule reduces to advertised^beta."""
    from searchy.queries import QueryType

    router = _router()
    qtype = QueryType.FACTUAL
    tools = router.layers[0]
    expected = np.array([t.advertised[qtype] ** router.beta for t in tools])
    expected = expected / expected.sum()
    assert np.allclose(router.routing_probabilities(0, qtype), expected)


def test_routes_each_query_through_both_layers() -> None:
    router = _router()
    queries = generate_queries(np.random.default_rng(7), n_per_type=5)
    records = [router.route(q, np.random.default_rng(7)) for q in queries]
    for rec in records:
        assert isinstance(rec, RouteRecord)
        assert rec.path[0] in RETRIEVE_NAMES
        assert rec.path[1] in PROCESS_NAMES
        assert len(rec.results) == 2


def test_tau_persists_and_changes_across_100_queries() -> None:
    router = _router()
    records = router.route_stream(
        generate_queries(np.random.default_rng(1)), np.random.default_rng(0)
    )
    assert len(records) == 100
    assert not np.allclose(router.tau, TAU0)  # pheromone actually moved
    # and the record snapshots let us audit the whole trajectory
    assert not np.allclose(records[0].tau_after, records[-1].tau_after)


def test_router_deterministic_under_seed() -> None:
    queries = generate_queries(np.random.default_rng(7))

    def run(seed: int) -> tuple[list[RouteRecord], np.ndarray]:
        router = _router()
        records = router.route_stream(queries, np.random.default_rng(seed))
        return records, router.tau.copy()

    rec_a, tau_a = run(42)
    rec_b, tau_b = run(42)
    assert np.allclose(tau_a, tau_b)
    assert [r.path for r in rec_a] == [r.path for r in rec_b]
    assert [r.reward for r in rec_a] == [r.reward for r in rec_b]

    rec_c, _ = run(43)
    assert [r.path for r in rec_c] != [r.path for r in rec_a]  # seeds matter


def test_deposit_clipped_at_zero_for_negative_rewards() -> None:
    assert deposit_amount(-0.5) == 0.0
    assert abs(deposit_amount(0.25) - 0.25) < 1e-12


def test_evaporation_fires_only_at_batch_boundaries() -> None:
    router = _router()
    records = router.route_stream(
        generate_queries(np.random.default_rng(2), n_per_type=3),  # 12 queries
        np.random.default_rng(5),
    )
    assert [r.evaporated for r in records] == [i % 10 == 9 for i in range(12)]


def test_rho_one_zeroes_pheromone_at_boundary() -> None:
    """rho=1 makes batch evaporation wipe tau: pins the update order
    (deposit first, then evaporate) exactly."""
    router = _router(rho=1.0)
    records = router.route_stream(
        generate_queries(np.random.default_rng(4), n_per_type=3),  # 12 queries
        np.random.default_rng(3),
    )
    # after query 10: deposit applied, then everything multiplied by (1-1)
    assert (records[9].tau_after == 0.0).all()
    # after query 11: only the fresh deposit is present, no evaporation
    assert np.isclose(records[10].tau_after.sum(), 2 * records[10].deposit)


def test_zero_pheromone_falls_back_to_uniform_probabilities() -> None:
    """All-tau-zero must not produce NaNs (numerical hygiene guard)."""
    from searchy.queries import QueryType

    router = _router()
    router.tau[:, :] = 0.0
    probs = router.routing_probabilities(0, QueryType.MATH)
    assert np.allclose(probs, 1.0 / 3.0)


def test_epsilon_one_forces_uniform_exploration() -> None:
    """With epsilon=1 every choice is uniform-random: all tools get traffic."""
    router = _router(epsilon=1.0)
    records = router.route_stream(
        generate_queries(np.random.default_rng(8)), np.random.default_rng(9)
    )
    assert {r.path[0] for r in records} == RETRIEVE_NAMES
    assert {r.path[1] for r in records} == PROCESS_NAMES


def test_process_layer_locks_onto_small_llm() -> None:
    """The one robust learning signal across seeds (diagnosis-log D3):
    small_llm is truly best for 3 of 4 types, and within 100 queries it
    holds the largest process-layer pheromone in every seed tried."""
    for seed in (0, 1, 2, 3, 4):
        router = _router()
        router.route_stream(generate_queries(np.random.default_rng(1)), np.random.default_rng(seed))
        process_tools = router.layers[1]
        winner = process_tools[int(router.tau[1].argmax())].name
        assert winner == "small_llm", f"seed {seed}: process winner was {winner}"