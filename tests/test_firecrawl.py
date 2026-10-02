"""Tests for the Firecrawl fixture layer (record/replay contract).

Implements FO.1 test coverage: record-then-replay identity, replay
determinism (the only randomness in an experiment is the router's seed),
fixture-miss failure, credit accounting, and no-live-call-by-default.
"""

from __future__ import annotations

import pytest

from searchy.firecrawl import FixtureCall, FixtureStore, FirecrawlOverlay


def _fake_live(endpoint, params):
    """A stand-in for the approved recording session; deterministic here."""
    resp = {"endpoint": endpoint, "echo": params, "content": "ok"}
    return resp, 1.0


def test_record_then_replay_identical(tmp_path):
    store_rec = FixtureStore(tmp_path / "fx.jsonl")
    rec = FirecrawlOverlay(mode="record", store=store_rec, live_call=_fake_live)
    a = rec.call("/search", {"q": "firecrawl docs", "limit": 5})
    b = rec.call("/scrape", {"url": "https://example.com", "format": "markdown"})

    store_rep = FixtureStore(tmp_path / "fx.jsonl")
    rep = FirecrawlOverlay(mode="replay", store=store_rep)
    ra = rep.call("/search", {"q": "firecrawl docs", "limit": 5})
    rb = rep.call("/scrape", {"url": "https://example.com", "format": "markdown"})
    assert ra.response == a.response
    assert rb.response == b.response
    assert ra.credits == a.credits
    # recorded latency is replayed verbatim (world frozen)
    assert ra.latency_ms == a.latency_ms


def test_replay_is_deterministic_across_loads(tmp_path):
    store = FixtureStore(tmp_path / "fx.jsonl")
    rec = FirecrawlOverlay(mode="record", store=store, live_call=_fake_live)
    rec.call("/map", {"url": "https://example.com", "limit": 20})

    s2 = FixtureStore(tmp_path / "fx.jsonl")
    r1 = FirecrawlOverlay(mode="replay", store=s2).call(
        "/map", {"limit": 20, "url": "https://example.com"}
    )
    s3 = FixtureStore(tmp_path / "fx.jsonl")
    r2 = FirecrawlOverlay(mode="replay", store=s3).call(
        "/map", {"url": "https://example.com", "limit": 20}
    )
    assert r1.response == r2.response
    assert r1.latency_ms == r2.latency_ms


def test_fixture_miss_fails_loudly(tmp_path):
    store = FixtureStore(tmp_path / "fx.jsonl")
    rep = FirecrawlOverlay(mode="replay", store=store)
    with pytest.raises(KeyError, match="fixture miss"):
        rep.call("/search", {"q": "never recorded"})


def test_credit_accounting(tmp_path):
    store = FixtureStore(tmp_path / "fx.jsonl")
    rec = FirecrawlOverlay(mode="record", store=store, live_call=_fake_live)
    for _ in range(3):
        rec.call("/search", {"q": "x"})
    assert store.total_calls() == 3
    assert store.total_credits() == pytest.approx(3.0)


def test_mode_validation():
    store = FixtureStore("/tmp/opencode/never.jsonl")
    with pytest.raises(ValueError, match="mode"):
        FirecrawlOverlay(mode="live", store=store)
    with pytest.raises(ValueError, match="live_call"):
        FirecrawlOverlay(mode="record", store=store)


def test_replay_never_calls_live(tmp_path):
    store = FixtureStore(tmp_path / "fx.jsonl")
    rec = FirecrawlOverlay(mode="record", store=store, live_call=_fake_live)
    rec.call("/search", {"q": "y"})
    rep = FirecrawlOverlay(
        mode="replay",
        store=FixtureStore(tmp_path / "fx.jsonl"),
        live_call=None,  # no live path even exists in replay
    )
    assert rep.live_call is None
    assert rep.call("/search", {"q": "y"}).response["content"] == "ok"
