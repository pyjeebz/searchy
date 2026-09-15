"""Simulated tool pool for Searchy.

Implements M6.2.

Six tools in two layers (3 "retrieve", 3 "process"). Each tool has a TRUE
quality profile per query type (designed so the best tool differs by type),
a token cost, and a latency. The ADVERTISED skill match (eta) is the true
profile plus seeded noise — deliberately misleading on two (tool, type)
pairs, which is what the colony must learn through experience.

Advertisements are properties of the tools, not of the experiment: they are
generated from a fixed module-level seed and are identical across every
experiment run and seed. Only per-call quality noise uses the caller's
generator, so ``call_tool`` is deterministic given (tool, query, generator
state).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from searchy.queries import Query, QueryType

LAYER_RETRIEVE = 0
LAYER_PROCESS = 1
TOOLS_PER_LAYER = 3

# Fixed seed for advertised-skill noise: ads must be stable across runs.
AD_NOISE_SEED = 20260915
AD_NOISE_SIGMA = 0.05
AD_MIN = 0.05  # never advertise a literally-zero skill

# Deliberately misleading (tool, type) advertisements: (tool, type) -> ad.
# These are the "ads" the colony must learn to distrust through experience.
MISLEADING_ADS: dict[tuple[str, QueryType], float] = {
    ("knowledge_base", QueryType.MATH): 0.90,  # true quality 0.35
    ("vector_db", QueryType.FACTUAL): 0.85,  # true quality 0.70
}


@dataclass(frozen=True)
class Tool:
    """One simulated tool: identity, true quality profile, costs, ads."""

    name: str
    layer: int
    true_quality: dict[QueryType, float]  # TRUE q(tool | type), in [0, 1]
    cost_tokens: int
    latency_ms: int
    advertised: dict[QueryType, float]  # noisy eta(tool | type), in [AD_MIN, 1]

    def expected_quality(self, qtype: QueryType) -> float:
        """True mean quality for a query type (no call noise)."""
        return self.true_quality[qtype]


@dataclass(frozen=True)
class ToolResult:
    """Outcome of calling one tool on one query."""

    quality: float  # in [0, 1]
    cost_tokens: int
    latency_ms: int


# TRUE quality profiles: best tool differs per type by design.
# Rows follow the design doc table (docs/design-searchy.md).
_TRUE_QUALITY: dict[str, dict[QueryType, float]] = {
    "web_search": {
        QueryType.FACTUAL: 0.95,
        QueryType.MATH: 0.25,
        QueryType.SUMMARIZATION: 0.55,
        QueryType.CODE: 0.60,
    },
    "vector_db": {
        QueryType.FACTUAL: 0.70,
        QueryType.MATH: 0.30,
        QueryType.SUMMARIZATION: 0.75,
        QueryType.CODE: 0.65,
    },
    "knowledge_base": {
        QueryType.FACTUAL: 0.80,
        QueryType.MATH: 0.35,
        QueryType.SUMMARIZATION: 0.50,
        QueryType.CODE: 0.40,
    },
    "small_llm": {
        QueryType.FACTUAL: 0.60,
        QueryType.MATH: 0.55,
        QueryType.SUMMARIZATION: 0.95,
        QueryType.CODE: 0.85,
    },
    "calculator": {
        QueryType.FACTUAL: 0.10,
        QueryType.MATH: 0.98,
        QueryType.SUMMARIZATION: 0.05,
        QueryType.CODE: 0.20,
    },
    "regex_processor": {
        QueryType.FACTUAL: 0.20,
        QueryType.MATH: 0.40,
        QueryType.SUMMARIZATION: 0.30,
        QueryType.CODE: 0.70,
    },
}

# (cost_tokens, latency_ms): good-for-type is deliberately NOT cheap.
_COST_LATENCY: dict[str, tuple[int, int]] = {
    "web_search": (1500, 800),
    "vector_db": (400, 120),
    "knowledge_base": (350, 150),
    "small_llm": (3000, 1200),
    "calculator": (200, 50),
    "regex_processor": (250, 100),
}

_LAYER: dict[str, int] = {
    "web_search": LAYER_RETRIEVE,
    "vector_db": LAYER_RETRIEVE,
    "knowledge_base": LAYER_RETRIEVE,
    "small_llm": LAYER_PROCESS,
    "calculator": LAYER_PROCESS,
    "regex_processor": LAYER_PROCESS,
}


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _build_advertised(name: str, rng: np.random.Generator) -> dict[QueryType, float]:
    """Advertised eta = true + noise, clipped; misleading pairs overridden."""
    ads: dict[QueryType, float] = {}
    for qtype, true_q in _TRUE_QUALITY[name].items():
        override = MISLEADING_ADS.get((name, qtype))
        if override is not None:
            ads[qtype] = override
        else:
            ads[qtype] = min(1.0, max(AD_MIN, true_q + rng.normal(0.0, AD_NOISE_SIGMA)))
    return ads


def build_tool_pool() -> dict[str, Tool]:
    """Build the 6-tool pool. Ads are drawn from the fixed AD_NOISE_SEED.

    Implements M6.2. Deterministic: every call returns an identical pool.
    """
    ad_rng = np.random.default_rng(AD_NOISE_SEED)
    pool: dict[str, Tool] = {}
    for name in _LAYER:
        cost, latency = _COST_LATENCY[name]
        pool[name] = Tool(
            name=name,
            layer=_LAYER[name],
            true_quality=dict(_TRUE_QUALITY[name]),
            cost_tokens=cost,
            latency_ms=latency,
            advertised=_build_advertised(name, ad_rng),
        )
    return pool


def tools_in_layer(pool: dict[str, Tool], layer: int) -> list[Tool]:
    """Tools of one layer, in a fixed (alphabetical) order."""
    return sorted((t for t in pool.values() if t.layer == layer), key=lambda t: t.name)


def call_tool(tool: Tool, query: Query, rng: np.random.Generator) -> ToolResult:
    """Call a tool on a query: quality with seeded per-call noise.

    Implements M6.2. Quality = true profile + N(0, 0.05) noise, clipped to
    [0, 1]. Deterministic given (tool, query, generator state): a fresh
    generator with the same seed yields the same result.
    """
    noise = rng.normal(0.0, AD_NOISE_SIGMA)
    quality = _clip01(tool.true_quality[query.qtype] + noise)
    return ToolResult(
        quality=quality,
        cost_tokens=tool.cost_tokens,
        latency_ms=tool.latency_ms,
    )