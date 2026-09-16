"""Run-level metrics for routed query streams.

Implements M6.5 (ROADMAP: "cumulative reward, final mean quality, mean
cost, learning curve").

Duck-typed on any record exposing ``reward`` and ``results`` — both
``RouteRecord`` (router) and ``BaselineRecord`` (baselines) qualify, so
every method is summarized by the same code.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

# "Final" performance = the last quarter of the 100-query stream (the
# router has had 75 queries to learn by then).
FINAL_WINDOW = 25


def path_quality(record: Any) -> float:
    """Realized quality product along the path (the reward's quality term)."""
    quality = 1.0
    for result in record.results:
        quality *= result.quality
    return quality


def summarize_run(records: Sequence[Any]) -> dict[str, float]:
    """Aggregates for one method's run over one stream.

    ``final_quality`` is the mean quality product over the last
    ``FINAL_WINDOW`` queries (or the whole run if shorter) — the
    after-learning number, as opposed to ``mean_quality`` over everything.
    """
    rewards = np.array([r.reward for r in records])
    qualities = np.array([path_quality(r) for r in records])
    costs = np.array([sum(res.cost_tokens for res in r.results) for r in records])
    latencies = np.array([sum(res.latency_ms for res in r.results) for r in records])
    window = min(FINAL_WINDOW, len(records))
    return {
        "n_queries": len(records),
        "cumulative_reward": float(rewards.sum()),
        "mean_reward": float(rewards.mean()),
        "mean_quality": float(qualities.mean()),
        "final_quality": float(qualities[-window:].mean()),
        "mean_cost_tokens": float(costs.mean()),
        "mean_latency_ms": float(latencies.mean()),
    }


def rolling_mean(values: Sequence[float], window: int = 10) -> np.ndarray:
    """Trailing rolling mean, same length as the input.

    The first ``window - 1`` points expand (mean of everything so far) so
    the learning curve has no NaN head. This is the M6.5 learning-curve
    smoother: window = one evaporation batch by default.
    """
    data = np.asarray(values, dtype=float)
    out = np.empty(len(data))
    for i in range(len(data)):
        lo = max(0, i - window + 1)
        out[i] = data[lo : i + 1].mean()
    return out