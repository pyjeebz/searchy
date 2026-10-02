"""Firecrawl client + fixture layer: record once, replay deterministically.

Implements FO.1 (charter v3 overlay module — built ONLY after Stage 4 and
human credit approval; this module exists so the recording session is a
two-minute operation, not a build).

Design (mirrors the project's fixture-first honesty rules):
- RECORD mode: each live API call is logged to a fixture file — endpoint,
  params, credits used, latency ms, and the full response. Recording is a
  single linear pass over the query stream; NO experiment logic runs live.
- REPLAY mode (the only mode experiments use): identical (endpoint,
  params) pairs return the recorded response + recorded latency +
  recorded credits. Seed-controlled router randomness is the ONLY
  randomness in a replayed experiment — the world is frozen.
- Missing key in replay = protocol error (fail loudly, never invent data).

The fixture format is JSONL (one call per line) so a recorded set is
diffable, greppable, and human-auditable: the entire real-world evidence
for the overlay fits in one file.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Firecrawl published credit costs (per-call, default plan) — cited in
# FO.2/FO.3. Credited here so the registry and the demo agree.
PUBLISHED_CREDITS: dict[str, float] = {
    "/search": 1.0,
    "/map": 1.0,
    "/scrape": 1.0,  # markdown: 1; json/product formats also 1 per call
}


@dataclass(frozen=True)
class FixtureCall:
    """One recorded Firecrawl call (the unit of real-world evidence)."""

    endpoint: str  # "/search" | "/map" | "/scrape"
    params: dict[str, Any]
    credits: float  # what Firecrawl charged (recorded, not assumed)
    latency_ms: float
    response: dict[str, Any]


class FixtureStore:
    """Append-only JSONL fixture file shared by record and replay."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._records: list[FixtureCall] = []
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    d = json.loads(line)
                    self._records.append(FixtureCall(**d))

    @property
    def records(self) -> list[FixtureCall]:
        return list(self._records)

    def append(self, call: FixtureCall) -> None:
        self._records.append(call)
        with self.path.open("a") as fh:
            fh.write(json.dumps(call.__dict__) + "\n")

    def lookup(self, endpoint: str, params: dict[str, Any]) -> FixtureCall | None:
        """First recorded call matching (endpoint, canonical params)."""
        canon = json.dumps(params, sort_keys=True)
        for r in self._records:
            if r.endpoint == endpoint and json.dumps(r.params, sort_keys=True) == canon:
                return r
        return None

    def total_credits(self) -> float:
        return sum(r.credits for r in self._records)

    def total_calls(self) -> int:
        return len(self._records)


class FirecrawlOverlay:
    """The record/replay client. Exactly one of the modes is live.

    ``record`` mode wraps a ``live_call`` callable (the human-approved
    recording session only — it costs credits). ``replay`` mode answers
    every request from the fixture store; a miss raises KeyError so a
    mis-scoped experiment fails loudly instead of inventing data.
    """

    def __init__(
        self,
        *,
        mode: str,
        store: FixtureStore,
        live_call: Any = None,
    ):
        if mode not in ("record", "replay"):
            raise ValueError(f"mode must be 'record' or 'replay', got {mode!r}")
        if mode == "record" and live_call is None:
            raise ValueError("record mode needs a live_call callable")
        self.mode = mode
        self.store = store
        self.live_call = live_call

    def call(self, endpoint: str, params: dict[str, Any]) -> FixtureCall:
        """One Firecrawl call — recorded live, or replayed from fixtures."""
        if self.mode == "replay":
            hit = self.store.lookup(endpoint, params)
            if hit is None:
                raise KeyError(
                    f"fixture miss for {endpoint} {params!r} — record it "
                    "first (human approval required; experiments never "
                    "call live)"
                )
            return hit
        t0 = time.perf_counter()
        response, credits = self.live_call(endpoint, params)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        call = FixtureCall(
            endpoint=endpoint,
            params=params,
            credits=float(credits),
            latency_ms=latency_ms,
            response=response,
        )
        self.store.append(call)
        return call

# --- FO.2: tool registry (published per-call credit costs) ---
# The registry maps the Searchy router's two layers onto real Firecrawl
# endpoints. "Advertised skill" = what the endpoint's metadata suggests
# it is good for (the honest analogue of the simulated tools' ads —
# endpoint docs are marketing too).

FIRECRAWL_REGISTRY: dict[str, dict[str, float]] = {
    # retrieve layer: where to look first
    "/search": {"credits": 1.0, "ads_docs": 0.6, "ads_news": 0.9, "ads_product": 0.7, "ads_factual": 0.8},
    "/map": {"credits": 1.0, "ads_docs": 0.8, "ads_news": 0.3, "ads_product": 0.5, "ads_factual": 0.5},
    # process layer: what to pull / how to render
    "/scrape": {"credits": 1.0, "ads_docs": 0.9, "ads_news": 0.8, "ads_product": 0.6, "ads_factual": 0.7},
}


def registry_tools() -> list[tuple[str, int, dict[str, float]]]:
    """(endpoint, layer, advertised skills) rows for the FO router."""
    layer_of = {"/search": 0, "/map": 0, "/scrape": 1}
    out = []
    for endpoint, meta in FIRECRAWL_REGISTRY.items():
        out.append((endpoint, layer_of[endpoint], meta))
    return out


# --- FO.3: query set (~25 queries x 4 types; the recording script ---
# The recording session (human-approved, ONE pass, <=$15) walks this list
# and records every (endpoint, params) the router's static baselines would
# call, plus the epsilon-exploration calls the router needs in replay —
# the fixture set must cover the router's whole reachable action set.

FO_QUERY_SET: list[dict[str, str]] = [
    # docs-lookup (7): would route /map or /search first, scrape markdown
    {"type": "docs-lookup", "q": "Firecrawl /search endpoint parameters limit depth"},
    {"type": "docs-lookup", "q": "Firecrawl API authentication header example"},
    {"type": "docs-lookup", "q": "Firecrawl /map endpoint max depth option"},
    {"type": "docs-lookup", "q": "Firecrawl rate limits per plan"},
    {"type": "docs-lookup", "q": "Firecrawl webhook crawl finished event"},
    {"type": "docs-lookup", "q": "Firecrawl SDK error codes"},
    {"type": "docs-lookup", "q": "Firecrawl /extract schema field types"},
    # news/current (6): /search first
    {"type": "news", "q": "Firecrawl funding announcement"},
    {"type": "news", "q": "Mendable Firecrawl latest release notes"},
    {"type": "news", "q": "web scraping legal news 2026"},
    {"type": "news", "q": "Firecrawl v2 API changes"},
    {"type": "news", "q": "open source crawlers comparison 2026"},
    {"type": "news", "q": "LLM agents web search tools news"},
    # structured-product (6): /scrape json or product format
    {"type": "structured-product", "q": "MacBook Air M4 price specs"},
    {"type": "structured-product", "q": "Sony WH-1000XM6 price"},
    {"type": "structured-product", "q": "Kindle Paperwhite 12th gen price"},
    {"type": "structured-product", "q": "Logitech MX Master 4 price"},
    {"type": "structured-product", "q": "Therabody Theragun price"},
    {"type": "structured-product", "q": "DJI Mini 5 Pro price specs"},
    # general-factual (6): /search or /scrape
    {"type": "general-factual", "q": "population of Lisbon 2026"},
    {"type": "general-factual", "q": "height of Mount Kilimanjaro"},
    {"type": "general-factual", "q": "current US Open champion"},
    {"type": "general-factual", "q": "who wrote Neuromancer"},
    {"type": "general-factual", "q": "chemical formula of caffeine"},
    {"type": "general-factual", "q": "distance Earth to Moon km"},
]
