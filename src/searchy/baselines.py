"""Non-learning baselines the pheromone router is measured against.

Implements M6.4 (spec: docs/design-searchy.md "baselines.py").

Four baselines share the router's world exactly — same two-layer route
shape, same ``call_tool`` per-call noise, same charter reward — and differ
only in how they pick tools:

* ``random``            — uniform tool per layer, re-drawn every query.
* ``greedy-cheapest``   — per layer, the tool minimizing the charter's own
                           penalty scale ``tokens/1e4 + ms/1e3``. Ignores
                           the query entirely (type-blind).
* ``greedy-advertised`` — per layer, argmax advertised skill (eta). Trusts
                           the ads forever, misleading ones included: the
                           strawman the router has to beat. The D2 ads
                           give it teeth — it loses math and
                           summarization against the oracle.
* ``oracle``            — per type, the expected-reward-best path over all
                           9 combinations, computed from TRUE profiles.
                           Not a real method: the upper-bound line in the
                           M6.5 plots.

Selection vs realization: the greedy/oracle picks are deterministic
functions of (pool, qtype); only ``random``'s picks and every ``call_tool``
quality draw consume the caller's ``np.random.Generator``. Realized
rewards are therefore directly comparable to the router's — the shared
things (query stream, pool, reward function, call-noise model) are shared,
while each method runs as a self-contained process on its own generator.
The oracle is the upper bound *in expectation* (its selection uses true
profiles); its realized rewards still face call noise like everyone's.

Records mirror the router's ``RouteRecord`` where M6.5 needs it
(``path`` / ``results`` / ``reward``), so the harness can treat all
methods uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from searchy.queries import Query, QueryType
from searchy.reward import COST_SCALE, LATENCY_SCALE, path_reward
from searchy.tools import (
    LAYER_PROCESS,
    LAYER_RETRIEVE,
    Tool,
    ToolResult,
    call_tool,
    tools_in_layer,
)


@dataclass(frozen=True)
class BaselineRecord:
    """One baseline-routed query, shaped like the router's RouteRecord."""

    query: Query
    path: tuple[str, str]  # (retrieve tool name, process tool name)
    results: tuple[ToolResult, ToolResult]
    reward: float  # raw charter reward of the realized path


BASELINE_NAMES: tuple[str, ...] = (
    "random",
    "greedy-cheapest",
    "greedy-advertised",
    "oracle",
)


def penalty_scale(tool: Tool) -> float:
    """The charter's own cost weight of a tool: tokens/1e4 + ms/1e3.

    greedy-cheapest argmins this per layer: it minimizes the penalty term
    of the reward while ignoring quality altogether.
    """
    return tool.cost_tokens / COST_SCALE + tool.latency_ms / LATENCY_SCALE


def expected_path_reward(retrieve: Tool, process: Tool, qtype: QueryType) -> float:
    """Charter reward of a path using TRUE quality profiles (no call noise).

    The oracle's selection quantity, and the upper-bound number M6.5 draws
    for the oracle line.
    """
    results = [
        ToolResult(
            quality=retrieve.expected_quality(qtype),
            cost_tokens=retrieve.cost_tokens,
            latency_ms=retrieve.latency_ms,
        ),
        ToolResult(
            quality=process.expected_quality(qtype),
            cost_tokens=process.cost_tokens,
            latency_ms=process.latency_ms,
        ),
    ]
    return path_reward(results)


def oracle_path(pool: dict[str, Tool], qtype: QueryType) -> tuple[str, str]:
    """Reward-best (retrieve, process) name pair for a type, true profiles.

    Brute-forces all 3x3 combinations by expected reward. Ties keep the
    alphabetically-first pair (tools_in_layer order), so this is
    deterministic and precomputable per type.
    """
    best_path: tuple[str, str] | None = None
    best_reward = float("-inf")
    for retrieve in tools_in_layer(pool, LAYER_RETRIEVE):
        for process in tools_in_layer(pool, LAYER_PROCESS):
            reward = expected_path_reward(retrieve, process, qtype)
            if reward > best_reward:
                best_path = (retrieve.name, process.name)
                best_reward = reward
    assert best_path is not None
    return best_path


def _execute(
    query: Query, retrieve: Tool, process: Tool, rng: np.random.Generator
) -> BaselineRecord:
    """Run one query through a fixed (or already-picked) tool pair."""
    results = (call_tool(retrieve, query, rng), call_tool(process, query, rng))
    return BaselineRecord(
        query=query,
        path=(retrieve.name, process.name),
        results=results,
        reward=path_reward(results),
    )


def run_random(
    pool: dict[str, Tool],
    queries: Sequence[Query],
    rng: np.random.Generator,
) -> list[BaselineRecord]:
    """Uniform random tool per layer, re-drawn every query. No learning."""
    retrieve_tools = tools_in_layer(pool, LAYER_RETRIEVE)
    process_tools = tools_in_layer(pool, LAYER_PROCESS)
    records = []
    for query in queries:
        retrieve = retrieve_tools[int(rng.integers(len(retrieve_tools)))]
        process = process_tools[int(rng.integers(len(process_tools)))]
        records.append(_execute(query, retrieve, process, rng))
    return records


def run_greedy_cheapest(
    pool: dict[str, Tool],
    queries: Sequence[Query],
    rng: np.random.Generator,
) -> list[BaselineRecord]:
    """Per layer, the cheapest tool by the charter penalty scale. No learning."""
    retrieve = min(tools_in_layer(pool, LAYER_RETRIEVE), key=penalty_scale)
    process = min(tools_in_layer(pool, LAYER_PROCESS), key=penalty_scale)
    return [_execute(q, retrieve, process, rng) for q in queries]


def run_greedy_advertised(
    pool: dict[str, Tool],
    queries: Sequence[Query],
    rng: np.random.Generator,
) -> list[BaselineRecord]:
    """Per layer, argmax advertised skill. Trusts the ads forever. No learning."""
    retrieve_tools = tools_in_layer(pool, LAYER_RETRIEVE)
    process_tools = tools_in_layer(pool, LAYER_PROCESS)
    records = []
    for query in queries:
        retrieve = max(retrieve_tools, key=lambda t: t.advertised[query.qtype])
        process = max(process_tools, key=lambda t: t.advertised[query.qtype])
        records.append(_execute(query, retrieve, process, rng))
    return records


def run_oracle(
    pool: dict[str, Tool],
    queries: Sequence[Query],
    rng: np.random.Generator,
) -> list[BaselineRecord]:
    """Per type, the true-profile reward-best path. Upper bound, not a method."""
    paths = {qtype: oracle_path(pool, qtype) for qtype in QueryType}
    records = []
    for query in queries:
        retrieve_name, process_name = paths[query.qtype]
        records.append(
            _execute(query, pool[retrieve_name], pool[process_name], rng)
        )
    return records


def run_baseline(
    name: str,
    pool: dict[str, Tool],
    queries: Sequence[Query],
    rng: np.random.Generator,
) -> list[BaselineRecord]:
    """Run one named baseline over a query stream (M6.5 entry point)."""
    runners = {
        "random": run_random,
        "greedy-cheapest": run_greedy_cheapest,
        "greedy-advertised": run_greedy_advertised,
        "oracle": run_oracle,
    }
    if name not in runners:
        raise ValueError(
            f"unknown baseline {name!r}; expected one of {BASELINE_NAMES}"
        )
    return runners[name](pool, queries, rng)