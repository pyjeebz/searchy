"""BoundedPheromoneRouter: MMAS bounds + stagnation restart, backported to
the Searchy router.

Implements M6-RT (ROADMAP Stage 4 payoff): backport MMAS-style pheromone
bounds and stagnation restart to the Searchy router, re-run M6.5/M6.6,
and measure whether resilience improves (recovery speed after sabotage)
with before/after plots.

The design is a deliberately minimal subclass of PheromoneRouter
(router.py): the transition rule, deposit clip (R1), batch evaporation
(R6) and ε-exploration are all INHERITED VERBATIM. Only the pheromone
maintenance changes, and only in two ways (the MMAS mechanism, Dorigo &
Stützle ch.3, as diagnosed in D3/D5):

1. BOUNDS (after every batch evaporation): τ is clipped to
   [tau_min, tau_max], computed from the run's realized rewards the way
   MMAS computes them from tour lengths:
       tau_max = Q / best_reward_so_far   (best = highest realized)
       tau_min = tau_max / gamma
   tau_min > 0 is the mechanism that keeps a collapsed tool reachable —
   the D5 diagnosis ("the colony cannot actively unlearn a once-popular
   tool") is precisely an unbounded-τ failure: after the sabotage, the
   lying ads (β=2) keep τ_web_search's SCORE competitive forever. With
   bounds, evaporation drags it to tau_min instead.

2. RESTART (stagnation): if no new best reward for `restart_after`
   consecutive queries, τ resets to tau_max on every edge — MMAS's
   restart, adapted to the query stream. The best-so-far is remembered
   in the bound computation, so the restart re-seeds exploration at a
   meaningful level rather than τ0.

Both mechanisms are the exact TSP fixes measured in M3.5/M4-L, mapped
onto the router's query world. Parameters follow the M6.3 conventions
(nothing tuned post-hoc): tau bounds use Q=1.0 (the router's deposit
scale), gamma=8 (tau_max/tau_min ratio; MMAS's default is instance-
scaled, here the pool has 3 tools per layer so a modest ratio bounds
the probability ratio at (8)^(alpha) = 8), restart_after=20 queries
(two evaporation batches).
"""

from __future__ import annotations

import numpy as np

from searchy.queries import Query
from searchy.reward import path_reward
from searchy.router import (
    EVAPORATION_BATCH,
    PheromoneRouter,
    RouteRecord,
)
from searchy.tools import (
    LAYER_PROCESS,
    LAYER_RETRIEVE,
    TOOLS_PER_LAYER,
    Tool,
    ToolResult,
    call_tool,
    tools_in_layer,
)

# M6-RT parameters (fixed a priori from the MMAS literature mapping;
# nothing tuned against the experiments).
TAU_MIN_MAX_RATIO = 8.0  # tau_max / tau_min
RESTART_AFTER = 20  # queries without a new best -> restart


class BoundedPheromoneRouter(PheromoneRouter):
    """PheromoneRouter + MMAS bounds + stagnation restart (M6-RT).

    Inherits the transition rule, deposit clip and ε-exploration from
    PheromoneRouter unchanged. Adds bounds recomputed after each batch
    evaporation and a restart after `restart_after` stagnant queries.
    """

    def __init__(
        self,
        pool: dict[str, Tool],
        *,
        tau_min_max_ratio: float = TAU_MIN_MAX_RATIO,
        restart_after: int = RESTART_AFTER,
        **kwargs,
    ) -> None:
        super().__init__(pool, **kwargs)
        self.tau_min_max_ratio = tau_min_max_ratio
        self.restart_after = restart_after
        self.best_reward = -np.inf
        self.since_improvement = 0
        self.tau_min = 0.0
        self.tau_max = float(self.tau.max())  # tau inits uniform at tau0
        self.restarts: list[int] = []  # 1-based query indices

    def _recompute_bounds(self) -> None:
        """MMAS bounds from realized rewards: Q/best, ratio-clipped."""
        if self.best_reward > 0:
            self.tau_max = self.q / self.best_reward
        else:
            self.tau_max = max(float(self.tau0), 1e-6)
        self.tau_min = self.tau_max / self.tau_min_max_ratio

    def route(self, query: Query, rng: np.random.Generator) -> RouteRecord:
        """Route one query; identical flow to PheromoneRouter.route plus
        bounds + restart bookkeeping at the batch boundary."""
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
        deposit = self.deposit_amount(reward) if hasattr(self, "deposit_amount") else self.q * max(0.0, reward)

        # best tracking for bounds + restart (query-level, like MMAS's
        # iteration-level)
        if reward > self.best_reward:
            self.best_reward = reward
            self.since_improvement = 0
        else:
            self.since_improvement += 1

        for layer, idx in enumerate(indices):
            self.tau[layer, idx] += deposit

        self._routed += 1
        evaporated = self._routed % self.evaporation_batch == 0
        if evaporated:
            self.tau *= 1.0 - self.rho
            # --- M6-RT: bounds after evaporation ---
            self._recompute_bounds()
            np.clip(self.tau, self.tau_min, self.tau_max, out=self.tau)
            # --- M6-RT: restart on stagnation ---
            if self.since_improvement >= self.restart_after:
                self.tau = np.full(self.tau.shape, self.tau_max)
                self.restarts.append(self._routed)
                self.since_improvement = 0

        return RouteRecord(
            query=query,
            path=(names[0], names[1]),
            results=(results[0], results[1]),
            reward=reward,
            deposit=deposit,
            evaporated=evaporated,
            tau_after=self.tau.copy(),
        )