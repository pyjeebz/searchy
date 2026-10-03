"""The ONE live recording session for the Firecrawl overlay (FO.1).

Implements FO.1's record phase: walks FO_QUERY_SET once, makes the live
calls the router + baselines need, logs (endpoint, params, credits,
latency, response) to a fixture file. After this pass, every experiment
replays the fixtures — no live calls, no credit spend, deterministic.

Recorded per query (the router's reachable action set):
- /search        {query, limit=5}                 — retrieve layer
- /map           {url: docs.firecrawl.dev, limit}  — retrieve layer
- /scrape        {url: top search hit, markdown}   — process layer
- /scrape        {url: top search hit, json}       — process layer
  (json = structured extraction for product/factual types)

Credits are taken as 1.0 per successful call (published default pricing;
failures record 0 and are visible in the fixture). Latency is wall time
per call. The session is resumable: already-recorded (endpoint, params)
pairs are skipped, so an interrupted pass never double-spends.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import urllib.request

from searchy.firecrawl import FIRECRAWL_REGISTRY, FO_QUERY_SET, FixtureStore

API = "https://api.firecrawl.dev/v2"
FIXTURE = Path("experiments/fixtures/firecrawl-overlay.jsonl")
DOCS_URL = "https://docs.firecrawl.dev"


def _live_call(endpoint: str, params: dict) -> tuple[dict, float]:
    """One live Firecrawl v2 call. Returns (response, credits)."""
    import os

    key = os.environ["FIRECRAWL_API_KEY"]
    req = urllib.request.Request(
        f"{API}{endpoint}",
        data=json.dumps(params).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.load(resp)
        credits = FIRECRAWL_REGISTRY[endpoint]["credits"]
        return body, credits
    except Exception as e:  # record failures too — they are evidence
        return {"success": False, "error": str(e)[:200]}, 0.0


def _top_hit(search_response: dict) -> str | None:
    """First web result URL from a recorded /search response."""
    try:
        web = search_response["data"]["web"]
        return web[0]["url"] if web else None
    except (KeyError, IndexError, TypeError):
        return None


def record(force: bool = False) -> FixtureStore:
    """Walk FO_QUERY_SET once, recording every call the router can reach.

    Resumable: pairs already in the fixture file are skipped unless
    ``force``. Prints a running credit total; NEVER called by tests.
    """
    if FIXTURE.exists() and not force:
        store = FixtureStore(FIXTURE)
        print(f"resuming: {store.total_calls()} calls already recorded")
    else:
        store = FixtureStore(FIXTURE)

    from searchy.firecrawl import FirecrawlOverlay

    rec = FirecrawlOverlay(mode="record", store=store, live_call=_live_call)

    for i, q in enumerate(FO_QUERY_SET):
        # 1. /search — the query text is the params (retrieve layer)
        r_search = rec.call(
            "/search",
            {"query": q["q"], "limit": 5, "sources": ["web"]},
        )
        top = _top_hit(r_search.response)

        # 2. /map — the docs-URL retrieve option (same params for every
        #    query: the endpoint ignores the query text; one canonical
        #    recording covers all 25 queries' /map option)
        if store.lookup("/map", {"url": DOCS_URL, "limit": 30}) is None:
            rec.call("/map", {"url": DOCS_URL, "limit": 30})

        # 3-4. /scrape the top hit, both formats (process layer)
        if top is not None:
            rec.call(
                "/scrape",
                {"url": top, "formats": ["markdown"], "onlyMainContent": True},
            )
            rec.call(
                "/scrape",
                {"url": top, "formats": ["json"]},
            )
        else:
            # canonical miss-recording so replay sees the same failure
            rec.call(
                "/scrape",
                {"url": "MISSING-HIT", "formats": ["markdown"]},
            )

        print(
            f"[{i+1}/{len(FO_QUERY_SET)}] {q['type']}: search ok, "
            f"scrape url={top!r} — credits so far {store.total_credits()}",
            flush=True,
        )

    print(
        f"DONE: {store.total_calls()} calls, {store.total_credits()} credits"
    )
    return store


if __name__ == "__main__":
    record()