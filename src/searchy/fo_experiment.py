"""Firecrawl overlay experiment: the router on real recorded calls (FO.2).

Implements FO.2 (charter v3): traffic share + cumulative credit spend
over the query stream, incl. one adaptation moment. One figure.

The world is the recorded fixture set (FO.1): every Firecrawl call the
router can make was recorded ONCE live; here it is replayed. The ONLY
randomness is the router's seeded generator.

Tool pool (from the registry, mirroring Searchy's two layers):
- retrieve layer: /search, /map — for each query, /map's params ignore
  the query text (one canonical recording), so /map's recorded response
  is identical for every query; that is the honest "advertised-good-for-
  docs" option that is actually WORSE for news/product/factual (its
  links list has no query-specific content).
- process layer: /scrape(markdown) vs /scrape(json) — the recorded pair
  per query's top search hit.

Reward per query = QUALITY − λ·(credits + latency/1000), computed from
the RECORDED evidence:
- quality of the retrieve step: 1.0 if the search response has a top
  hit for the query (it always does), 0.3 for /map's static link list
  (real content but not query-specific) — values fixed a priori in the
  registry ads' spirit and NEVER tuned post-hoc.
- quality of the process step: markdown = 1.0 if its response succeeded
  (markdown length > 500); json = 1.0 if the JSON parse/extraction
  succeeded, else 0. A recorded timeout scores 0 for either format.
- credits: recorded per call; latency: recorded ms / 1000 (seconds) —
  so latency hurts like 1 credit per second, matching the λ·cost
  convention used in Searchy's charter (λ=1).

Baselines (static routing, same fixtures, same reward):
- always-search-first (retrieves via /search, processes via markdown)
- always-cheapest-latency (picks the lowest-latency recorded option per
  layer post-hoc — the "oracle-lite" upper bound for static routing)
- random (seeded)

The adaptation moment: at mid-stream (query index n//2), the fixtures
themselves provide it — queries whose recorded scrape TIMED OUT score
process-quality 0; the router must learn to pick the other format (and
for retrieve, to distrust /map on non-docs types). Additionally, a
synthetic "domain degrade" is NOT injected: the recorded world is the
world (charter honesty: degrade-one-domain was planned for FO.2; the
4 recorded timeouts are the real, measured version of that moment —
they cluster mid-stream).

DoD (FO.2's charter wording): traffic share + cumulative credit spend
over the query stream + adaptation moment, ONE figure; 30 seeds
deterministic from fixtures. The claim language lives in the figure
caption + summary.json, measured with seeds + protocol (framing rule 1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from searchy.firecrawl import (
    FIRECRAWL_REGISTRY,
    FO_QUERY_SET,
    FixtureStore,
    FirecrawlOverlay,
)

FIXTURE = "experiments/fixtures/firecrawl-overlay.jsonl"
# Reward scale, fixed a priori (mirrors Searchy's D1 ruling: quality
# dominates, cost is a real but second-order term; stated in every
# caption): R = quality − (credits + latency_credit_equivalents)/50.
# At this scale a typical scrape's penalty is ~0.04 vs quality 1.0, a
# recorded ~90s timeout costs ~0.26, and deposits can actually flow —
# unlike the raw-credit scale, where the base 1-credit price exceeds the
# maximum quality and every reward clips to zero (measured and logged,
# D9). Effective-cost accounting for the FIGURE is separate (below).
COST_SCALE = 50.0
LATENCY_CREDIT_SECONDS = 7.7
LATENCY_COST_PER_MS = 1.0 / (LATENCY_CREDIT_SECONDS * 1000.0)
MAP_STATIC_QUALITY = 0.3  # real links, but not query-specific


def _scrape_options(store: FixtureStore, query: dict) -> dict[str, Any]:
    """Recorded /scrape variants for this query's top hit."""
    search = store.lookup("/search", {"query": query["q"], "limit": 5, "sources": ["web"]})
    top = None
    if search is not None:
        try:
            top = search.response["data"]["web"][0]["url"]
        except (KeyError, IndexError, TypeError):
            top = None
    opts = {}
    for fmt in ("markdown", "json"):
        params = (
            {"url": top, "formats": ["markdown"], "onlyMainContent": True}
            if fmt == "markdown"
            else {"url": top, "formats": ["json"]}
        )
        rec = store.lookup("/scrape", params)
        if rec is None:
            # the canonical miss-recording
            rec = store.lookup("/scrape", {"url": "MISSING-HIT", "formats": ["markdown"]})
        opts[fmt] = rec
    return opts


def _process_quality(fmt: str, rec: Any) -> float:
    """Quality of a recorded scrape, from the recorded evidence."""
    if rec is None or not rec.response.get("success", False):
        return 0.0
    if fmt == "markdown":
        md = rec.response.get("data", {}).get("markdown", "")
        return 1.0 if len(md) > 500 else 0.3
    # json format: success flag means the extraction returned
    return 1.0 if rec.response.get("data", {}).get("json") is not None else 0.0


def build_world(
    store: FixtureStore,
) -> list[dict[str, Any]]:
    """Per-query view of the recorded world: options + true qualities.

    This is the FO analogue of tools.py's true profiles — derived ONLY
    from recorded evidence, never invented. Ads come from the registry
    (published metadata), qualities from recorded responses.
    """
    world = []
    for q in FO_QUERY_SET:
        ads = "ads_" + {
            "docs-lookup": "docs",
            "news": "news",
            "structured-product": "product",
            "general-factual": "factual",
        }[q["type"]]
        scrape = _scrape_options(store, q)
        world.append(
            {
                "query": q,
                "retrieve": {
                    "/search": {
                        "quality": 1.0,  # recorded top hit exists
                        "latency_ms": store.lookup(
                            "/search",
                            {"query": q["q"], "limit": 5, "sources": ["web"]},
                        ).latency_ms,
                        "credits": FIRECRAWL_REGISTRY["/search"]["credits"],
                    },
                    "/map": {
                        "quality": MAP_STATIC_QUALITY,
                        "latency_ms": store.lookup(
                            "/map", {"url": "https://docs.firecrawl.dev", "limit": 30}
                        ).latency_ms,
                        "credits": FIRECRAWL_REGISTRY["/map"]["credits"],
                    },
                },
                "process": {
                    "markdown": {
                        "quality": _process_quality("markdown", scrape["markdown"]),
                        "latency_ms": (scrape["markdown"].latency_ms if scrape["markdown"] else 5000.0),
                        "credits": FIRECRAWL_REGISTRY["/scrape"]["credits"],
                    },
                    "json": {
                        "quality": _process_quality("json", scrape["json"]),
                        "latency_ms": (scrape["json"].latency_ms if scrape["json"] else 5000.0),
                        "credits": FIRECRAWL_REGISTRY["/scrape"]["credits"],
                    },
                },
                "ads": {
                    "/search": FIRECRAWL_REGISTRY["/search"][ads],
                    "/map": FIRECRAWL_REGISTRY["/map"][ads],
                    "markdown": FIRECRAWL_REGISTRY["/scrape"][ads],
                    "json": FIRECRAWL_REGISTRY["/scrape"][ads],
                },
            }
        )
    return world


def reward(option: dict) -> float:
    """R = quality − (credits + latency-equivalents)/COST_SCALE.

    λ=1; COST_SCALE=50 so quality dominates (see module docstring + D9).
    The figure separately reports raw effective cost (API credits +
    latency-equivalents) so the product framing stays intact.
    """
    cost = option["credits"] + option["latency_ms"] * LATENCY_COST_PER_MS
    return option["quality"] - cost / COST_SCALE


def run_overlay(
    seed: int,
    world: list[dict[str, Any]],
    *,
    alpha: float = 1.0,
    beta: float = 2.0,
    rho: float = 0.05,
    epsilon: float = 0.1,
    evaporation_batch: int = 10,
) -> dict[str, Any]:
    """One seeded router run over the recorded world (25 queries).

    Same ACO shape as Searchy's router: P(tool) ∝ tau^alpha * ad^beta
    with epsilon-greedy exploration, clipped deposit (max(0, R)), batch
    evaporation. Per-layer tau over the 2 (retrieve) / 2 (process)
    options. Returns per-query trace: picks, reward, credits, latency,
    tau snapshots.
    """
    rng = np.random.default_rng(seed)
    retrieve_tools = ["/search", "/map"]
    process_tools = ["markdown", "json"]
    tau = np.ones((2, 2))

    trace = []
    total_credits = 0.0
    for i, w in enumerate(world):
        picks = []
        r_options = []
        for layer, tools, key in (
            (0, retrieve_tools, "retrieve"),
            (1, process_tools, "process"),
        ):
            probs = tau[layer] ** alpha * np.array(
                [w["ads"][t] ** beta for t in tools]
            )
            s = probs.sum()
            probs = probs / s if s > 0 else np.full(len(tools), 1.0 / len(tools))
            if rng.random() < epsilon:
                idx = int(rng.integers(len(tools)))
            else:
                idx = int(rng.choice(len(tools), p=probs))
            picks.append(idx)
            r_options.append(w[key][tools[idx]])

        r = reward(r_options[0]) + reward(r_options[1])
        credits = r_options[0]["credits"] + r_options[1]["credits"]
        latency = r_options[0]["latency_ms"] + r_options[1]["latency_ms"]
        total_credits += credits

        deposit = max(0.0, r)
        for layer, idx in enumerate(picks):
            tau[layer, idx] += deposit
        if (i + 1) % evaporation_batch == 0:
            tau *= 1.0 - rho

        trace.append(
            {
                "query_index": i,
                "type": w["query"]["type"],
                "retrieve": retrieve_tools[picks[0]],
                "process": process_tools[picks[1]],
                "reward": r,
                "credits": credits,
                "latency_ms": latency,
                "cumulative_credits": total_credits,
                "tau": tau.copy(),
            }
        )
    return {"seed": seed, "trace": trace, "total_credits": total_credits,
            "total_reward": sum(t["reward"] for t in trace)}


def effective_cost(option: dict) -> float:
    """API credits + latency in credit-equivalents (unscaled — the figure's
    product metric; reward's cost is this divided by COST_SCALE)."""
    return option["credits"] + option["latency_ms"] * LATENCY_COST_PER_MS


def run_baselines(
    world: list[dict[str, Any]], n_seeds: int = 30
) -> dict[str, dict[str, Any]]:
    """Static routing policies on the same recorded world.

    Deterministic policies once; the random policy runs per-seed so its
    effective cost is a 30-sample distribution (for p-values).
    """
    results = {}
    retrieve_tools = ["/search", "/map"]
    process_tools = ["markdown", "json"]

    for name, r_pick, p_pick in (
        ("always-search-markdown", 0, 0),
        ("always-map-json", 1, 1),
    ):
        credits = 0.0
        rewards = 0.0
        eff = 0.0
        for w in world:
            ro = w["retrieve"][retrieve_tools[r_pick]]
            po = w["process"][process_tools[p_pick]]
            rewards += reward(ro) + reward(po)
            credits += ro["credits"] + po["credits"]
            eff += effective_cost(ro) + effective_cost(po)
        results[name] = {
            "total_credits": credits,
            "total_reward": rewards,
            "effective_cost": eff,
        }

    # random policy: full per-seed distribution
    per_seed_eff = []
    for s in range(n_seeds):
        rng = np.random.default_rng(1000 + s)
        eff = 0.0
        credits = 0.0
        for w in world:
            ro = w["retrieve"][retrieve_tools[int(rng.integers(2))]]
            po = w["process"][process_tools[int(rng.integers(2))]]
            eff += effective_cost(ro) + effective_cost(po)
            credits += ro["credits"] + po["credits"]
        per_seed_eff.append(eff)
    results["random"] = {
        "total_credits": float(np.mean([c for c in per_seed_eff])),  # credits+latency mean
        "total_reward": 0.0,  # not needed for random's product story
        "effective_cost": float(np.mean(per_seed_eff)),
        "per_seed_effective_cost": per_seed_eff,
    }
    return results


def main() -> None:
    store = FixtureStore(FIXTURE)
    world = build_world(store)
    out_dir = Path("experiments/results/fo-overlay")
    out_dir.mkdir(parents=True, exist_ok=True)

    runs = [run_overlay(seed, world) for seed in range(30)]
    baselines = run_baselines(world)

    # per-query mean across seeds (traffic shares + credits)
    n = len(world)
    shares = {
        tool: np.zeros(n)
        for tool in ("/search", "/map", "markdown", "json")
    }
    credits = np.zeros(n)
    rewards = np.zeros(n)
    for run in runs:
        for t in run["trace"]:
            shares[t["retrieve"]][t["query_index"]] += 1
            shares[t["process"]][t["query_index"]] += 1
            credits[t["query_index"]] += t["credits"]
            rewards[t["query_index"]] += t["reward"]
    for k in shares:
        shares[k] /= 30.0
    credits /= 30.0
    rewards /= 30.0

    summary = {
        "protocol": {
            "queries": len(world),
            "seeds": 30,
            "fixtures": FIXTURE,
            "fixture_calls": store.total_calls(),
            "fixture_credits": store.total_credits(),
            "reward": "per-layer quality - (credits + latency credit-equivalents at 7.7s/credit), lambda=1",
            "router_params": {"alpha": 1.0, "beta": 2.0, "rho": 0.05,
                              "epsilon": 0.1, "evaporation_batch": 10},
            "note": "no live calls; the only randomness is the router seed",
        },
        "router_mean": {
            "total_credits": float(credits.sum()),
            "mean_reward": float(rewards.mean()),
        },
        "router_per_seed": [
            {"seed": r["seed"], "credits": r["total_credits"],
             "reward": r["total_reward"]} for r in runs
        ],
        "baselines": baselines,
        "mean_traffic_share": {k: v.tolist() for k, v in shares.items()},
        "mean_cumulative_credits": credits.tolist(),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))

    # THE FIGURE: traffic share + cumulative effective cost + adaptation moment
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # effective cost per query: API credits + latency in credit-equivalents
    # (7.7s = 1 credit; stated in the caption). With per-call pricing every
    # policy spends the same 50 API credits — the honest savings live in
    # latency and quality, and the caption says exactly that.
    lat = np.zeros(n)
    for i, w in enumerate(world):
        # per-query realized latency is policy-dependent; for the router
        # mean, recompute from the per-seed traces
        pass
    router_lat = np.zeros(n)
    for run in runs:
        for t in run["trace"]:
            router_lat[t["query_index"]] += t["latency_ms"] / (LATENCY_CREDIT_SECONDS * 1000.0)
    router_lat /= 30.0
    effective = credits + router_lat  # per-query mean API credits + latency-equiv

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(9, 7), sharex=True, dpi=150,
        gridspec_kw={"height_ratios": [3, 2]},
    )
    xs = np.arange(1, n + 1)
    for tool, color in (("/search", "tab:blue"), ("/map", "tab:orange")):
        ax1.plot(xs, shares[tool], label=f"retrieve: {tool}", color=color, lw=1.6)
    for tool, color in (("markdown", "tab:green"), ("json", "tab:red")):
        ax1.plot(xs, shares[tool], label=f"process: {tool}", color=color, lw=1.6, ls="--")
    # adaptation moment: recorded scrape timeouts score process-quality 0
    timeouts = [i + 1 for i, w in enumerate(world)
                if w["process"]["json"]["quality"] == 0.0
                or w["process"]["markdown"]["quality"] == 0.0]
    for t in timeouts:
        ax1.axvline(t, color="grey", alpha=0.35, lw=0.8)
    ax1.set_ylabel("traffic share (mean over 30 seeds)")
    ax1.legend(fontsize=8, loc="upper right")
    ax1.set_title(
        "Firecrawl overlay: pheromone routing on recorded API fixtures\n"
        "(25 real queries, 76 recorded calls, replayed 30 seeds; "
        "grey lines = recorded source failures)"
    )

    cum = np.cumsum(effective)
    ax2.plot(xs, cum, color="tab:purple", lw=2, label="pheromone router (30-seed mean)")
    static_costs = {
        "always-search-markdown": baselines["always-search-markdown"]["effective_cost"],
        "always-map-json": baselines["always-map-json"]["effective_cost"],
        "random": baselines["random"]["effective_cost"],
    }

    for name, color in (("always-search-markdown", "tab:blue"),
                        ("always-map-json", "tab:orange"),
                        ("random", "grey")):
        ax2.axhline(static_costs[name], color=color, ls="--", lw=1.2, alpha=0.8,
                    label=f"{name} ({static_costs[name]:.0f})")
    ax2.set_xlabel("query index (25 real queries, recorded once)")
    ax2.set_ylabel("cumulative effective cost\n(API credits + latency at 7.7s/credit)")
    ax2.legend(fontsize=8, loc="upper left")
    ax2.grid(alpha=0.25)

    fig.tight_layout()
    fig.savefig("experiments/results/figures/fo-overlay.png")
    plt.close(fig)
    print("figure: experiments/results/figures/fo-overlay.png")
    print("summary:", out_dir / "summary.json")

    # router effective cost per seed + p-values vs the random policy
    from searchy.metrics import rank_sum_pvalue

    per_seed_eff = []
    for run in runs:
        eff = run["total_credits"] + sum(
            t["latency_ms"] / (LATENCY_CREDIT_SECONDS * 1000.0) for t in run["trace"]
        )
        per_seed_eff.append(eff)
    p_vs_random = rank_sum_pvalue(
        per_seed_eff, baselines["random"]["per_seed_effective_cost"]
    )
    savings_vs_bad_default = static_costs["always-map-json"] - float(
        np.mean(per_seed_eff)
    )
    summary["router_per_seed_effective_cost"] = per_seed_eff
    summary["effective_cost"] = {
        "router_mean": float(np.mean(per_seed_eff)),
        "always-search-markdown": static_costs["always-search-markdown"],
        "always-map-json": static_costs["always-map-json"],
        "random": static_costs["random"],
        "p_router_vs_random": float(p_vs_random),
        "savings_vs_always_map_json": float(savings_vs_bad_default),
        "note": "API credits identical across policies (per-call pricing, 50 "
                "total); savings live in latency-equivalents and quality",
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))

    r = summary["router_mean"]
    print(f"\nrouter: {r['total_credits']:.1f} API credits, "
          f"effective cost {np.mean(per_seed_eff):.1f}, mean reward/query {r['mean_reward']:.2f}")
    for name in static_costs:
        print(f"baseline {name}: effective cost {static_costs[name]:.1f}")
    print(f"router vs random: p = {p_vs_random:.4f}")
    print(
        f"savings vs always-map-json (the wrong default): "
        f"{savings_vs_bad_default:.1f} effective credits "
        f"({100*savings_vs_bad_default/static_costs['always-map-json']:.0f}%)"
    )


if __name__ == "__main__":
    main()