"""Path reward for Searchy.

Implements M6.3 (utility function specified in the design doc, M6.1):

    R(path) = product of tool qualities along path
              - lambda * (total_cost / 1e4 + total_latency / 1e3)

Quality dominates by design: tool costs are scaled (see tools.py and
diagnosis-log D1) so the penalty term lands well below the achievable
quality products — R can still go negative on a bad enough path, but the
reward-best path per query type is clearly positive.
"""

from __future__ import annotations

from typing import Sequence

from searchy.tools import ToolResult

LAMBDA = 1.0
COST_SCALE = 1e4  # tokens
LATENCY_SCALE = 1e3  # ms


def path_penalty(results: Sequence[ToolResult], lam: float = LAMBDA) -> float:
    """lambda * (total_tokens/1e4 + total_latency_ms/1e3) for a path."""
    tokens = sum(r.cost_tokens for r in results)
    latency = sum(r.latency_ms for r in results)
    return lam * (tokens / COST_SCALE + latency / LATENCY_SCALE)


def path_reward(results: Sequence[ToolResult], lam: float = LAMBDA) -> float:
    """R(path): product of tool qualities minus the scaled cost penalty."""
    quality = 1.0
    for r in results:
        quality *= r.quality
    return quality - path_penalty(results, lam)