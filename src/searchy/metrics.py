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

def rank_sum_pvalue(a: Sequence[float], b: Sequence[float]) -> float:
    """Two-sided Wilcoxon rank-sum (Mann-Whitney U) p-value.

    Implements M4-L (stats harness reused for every later comparison,
    including Stage 5's). Normal approximation with tie correction — the
    standard for n=30-per-group exact-when-small; we use the tie-corrected
    normal approximation throughout and state it in every table caption.
    """
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        raise ValueError("both samples must be non-empty")
    pooled = np.concatenate([x, y])
    order = np.argsort(pooled, kind="stable")
    ranks = np.empty(len(pooled))
    # average ranks for ties
    sorted_vals = pooled[order]
    i = 0
    while i < len(pooled):
        j = i
        while j + 1 < len(pooled) and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    r1 = ranks[:n1].sum()
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u = min(u1, n1 * n2 - u1)
    mu = n1 * n2 / 2.0
    # tie-corrected variance (Mann-Whitney normal approximation)
    _, counts = np.unique(pooled, return_counts=True)
    n = len(pooled)
    tie_sum = (counts**3 - counts).sum()
    sigma_sq = (n1 * n2 / 12.0) * (
        (n + 1) - tie_sum / (n * (n - 1))
    )
    if sigma_sq <= 0:
        return 1.0
    z = (u - mu) / np.sqrt(sigma_sq)
    return float(2.0 * (1.0 - _norm_cdf(abs(z))))


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via the error function (no scipy dependency)."""
    import math

    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
