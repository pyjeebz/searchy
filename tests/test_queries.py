"""Tests for synthetic query generation.

Implements M6.2 DoD: generate the 100 queries deterministically under seed.
"""

import numpy as np

from searchy.queries import N_QUERIES, N_PER_TYPE, Query, QueryType, generate_queries


def test_generates_100_queries_25_per_type() -> None:
    queries = generate_queries(np.random.default_rng(0))
    assert len(queries) == N_QUERIES == 100
    counts = {qt: 0 for qt in QueryType}
    for q in queries:
        counts[q.qtype] += 1
    assert all(c == N_PER_TYPE for c in counts.values())


def test_deterministic_under_seed() -> None:
    a = generate_queries(np.random.default_rng(42))
    b = generate_queries(np.random.default_rng(42))
    assert a == b


def test_different_seeds_differ() -> None:
    a = generate_queries(np.random.default_rng(1))
    b = generate_queries(np.random.default_rng(2))
    assert a != b


def test_stream_is_interleaved_not_grouped() -> None:
    queries = generate_queries(np.random.default_rng(0))
    first_four = [q.qtype for q in queries[:4]]
    assert len(set(first_four)) > 1  # not type-blocked


def test_payloads_are_nonempty_strings() -> None:
    for q in generate_queries(np.random.default_rng(7)):
        assert isinstance(q.payload, str) and len(q.payload) > 0


def test_payloads_vary_within_type() -> None:
    queries = generate_queries(np.random.default_rng(3))
    for qt in QueryType:
        payloads = {q.payload for q in queries if q.qtype == qt}
        assert len(payloads) > 10  # 25 queries should not collapse to ~few payloads


def test_query_is_hashable_and_frozen() -> None:
    q = generate_queries(np.random.default_rng(0))[0]
    assert isinstance(q, Query)
    try:
        q.payload = "mutated"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("Query should be frozen")