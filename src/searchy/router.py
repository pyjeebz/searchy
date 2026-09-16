"""ACO pheromone router: the learning core of Searchy.

Implements M6.3.

Each query is an "ant" that walks the two layers: it picks one retrieve
tool, then one process tool, with transition probabilities

    P(tool_j | layer l, type t) ∝ tau[l][j]**alpha * eta[j][t]**beta

where tau is a single shared 2x3 pheromone matrix persisted across queries
(design risk R3) and eta is the tool's advertised skill — including the two
deliberately misleading ads from tools.py. With probability epsilon the ant
ignores the probabilities and explores uniformly; that safeguard is what
keeps a misleading ad from permanently trapping the colony.

Updates follow the kickoff rulings: deposit immediately after each query
(R6), clipped at >= 0 for negative rewards (R1), added to both edges of the
path; evaporate tau *= (1 - rho) at every batch boundary of
``evaporation_batch`` queries, after that query's deposit.

All randomness flows through the caller's ``np.random.Generator``; two
routers fed the same seed and the same query stream produce identical
trajectories.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from searchy.queries import Query, QueryType
from searchy.reward import path_reward
from searchy.tools import (
    LAYER_PROCESS,
    LAYER_RETRIEVE,
    TOOLS_PER_LAYER,
    Tool,
    ToolResult,
    call_tool,
    tools_in_layer,
)

# Starting parameters (design doc, M6.1).
ALPHA = 1.0  # pheromone weight
BETA = 2.0  # advertised-skill weight
RHO = 0.05  # evaporation rate, applied per batch
EPSILON = 0.1  # uniform-exploration probability (the safeguard)
Q_DEPOSIT = 1.0  # deposit scale
TAU0 = 1.0  # initial pheromone on every edge
EVAPORATION_BATCH = 10  # queries between evaporations
N_LAYERS = 2

_LAYERS: tuple[int, ...] = (LAYER_RETRIEVE, LAYER_PROCESS)


@dataclass(frozen=True)
class RouteRecord:
    """One routed query: the path taken and everything needed to audit it."""

    query: Query
    path: tuple[str, str]  # (retrieve tool name, process tool name)
    results: tuple[ToolResult, ToolResult]
    reward: float  # raw R(path); can be negative — metrics use this
    deposit: float  # Q * max(0, R) actually added to each chosen edge
    evaporated: bool  # did batch evaporation fire right after this query
    tau_after: np.ndarray  # pheromone snapshot after this query's updates


def deposit_amount(reward: float, q: float = Q_DEPOSIT) -> float:
    """Pheromone to add per edge for a path reward.

    Negative rewards deposit nothing (kickoff ruling R1): the raw reward is
    kept for metrics, but pheromone only ever grows from deposits —
    evaporation is what shrinks it.
    """
    return q * max(0.0, reward)


class PheromoneRouter:
    """Routes queries through the tool pool using ACO transition rules."""

    def __init__(
        self,
        pool: dict[str, Tool],
        *,
        alpha: float = ALPHA,
        beta: float = BETA,
        rho: float = RHO,
        epsilon: float = EPSILON,
        q: float = Q_DEPOSIT,
        tau0: float = TAU0,
        evaporation_batch: int = EVAPORATION_BATCH,
    ) -> None:
        self.alpha = alpha
        self.beta = beta
        self.rho = rho
        self.epsilon = epsilon
        self.q = q
        self.evaporation_batch = evaporation_batch
        # Fixed tool order per layer (alphabetical) — tau columns are stable.
        self.layers: list[list[Tool]] = [
            tools_in_layer(pool, layer) for layer in _LAYERS
        ]
        self.tau: np.ndarray = np.full((N_LAYERS, TOOLS_PER_LAYER), float(tau0))
        self._routed = 0

    def routing_probabilities(self, layer: int, qtype: QueryType) -> np.ndarray:
        """P(tool | layer, type) — the effective routing distribution.

        tau^alpha * advertised^beta, normalized to sum to 1. If every score
        is zero (all pheromone evaporated away under an extreme rho), fall
        back to uniform — numerical hygiene, not a learning rule.
        """
        tools = self.layers[layer]
        scores = self.tau[layer] ** self.alpha * np.array(
            [t.advertised[qtype] ** self.beta for t in tools]
        )
        total = float(scores.sum())
        if total <= 0.0:
            return np.full(len(tools), 1.0 / len(tools))
        return scores / total

    def _choose(self, probs: np.ndarray, rng: np.random.Generator) -> int:
        """epsilon-greedy: explore uniformly, else sample the transition rule."""
        if rng.random() < self.epsilon:
            return int(rng.integers(len(probs)))
        return int(rng.choice(len(probs), p=probs))

    def route(self, query: Query, rng: np.random.Generator) -> RouteRecord:
        """Route one query through both layers, then update pheromones.

        Implements M6.3: choose + call a retrieve tool, choose + call a
        process tool, compute the path reward, deposit immediately (clipped
        at >= 0) on both chosen edges, evaporate at batch boundaries.
        """
        names: list[str] = []
        indices: list[int] = []
        results: list[ToolResult] = []
        for layer, tools in enumerate(self.layers):
            idx = self._choose(self.routing_probabilities(layer, query.qtype), rng)
            tool = tools[idx]
            names.append(tool.name)
            indices.append(idx)
            results.append(call_tool(tool, query, rng))

        reward = path_reward(results)
        deposit = deposit_amount(reward, self.q)
        for layer, idx in enumerate(indices):
            self.tau[layer, idx] += deposit

        self._routed += 1
        evaporated = self._routed % self.evaporation_batch == 0
        if evaporated:
            self.tau *= 1.0 - self.rho

        return RouteRecord(
            query=query,
            path=(names[0], names[1]),
            results=(results[0], results[1]),
            reward=reward,
            deposit=deposit,
            evaporated=evaporated,
            tau_after=self.tau.copy(),
        )

    def route_stream(
        self, queries: Sequence[Query], rng: np.random.Generator
    ) -> list[RouteRecord]:
        """Route a whole query stream in order (convenience for runners)."""
        return [self.route(q, rng) for q in queries]