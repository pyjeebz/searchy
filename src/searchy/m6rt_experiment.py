"""M6-RT: re-run M6.5/M6.6 with the bounded router; before/after plots.

Implements M6-RT (ROADMAP Stage 4 payoff). Protocol is the committed
M6.5/M6.6 protocol VERBATIM (same shared stream, same 5 seeds, same
M6.3 parameters, same sabotage event) — the ONLY change is the router
class: PheromoneRouter -> BoundedPheromoneRouter (MMAS bounds + restart,
the M3.5 mechanisms mapped onto the query world).

DoD: before/after comparison plots (comparison convergence + sabotage
money plot), plus the honest verdict on whether resilience improved
(recovery speed after sabotage — the D5 before-picture).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from searchy.baselines import run_baseline
from searchy.metrics import summarize_run
from searchy.queries import generate_queries
from searchy.router import PheromoneRouter
from searchy.router_mmas import BoundedPheromoneRouter
from searchy.tools import build_tool_pool

N_SEEDS = 5
QUERY_SEED = 100
SABOTAGE_EVENT = 50  # 1-based query index


def _apply_sabotage(pool, router):
    """Swap the sabotaged web_search into pool + router's cached layers
    (the M6.6 protocol: environment change, zero learning-machinery change).
    """
    from searchy.tools import Tool

    ws = pool["web_search"]
    sab = Tool(
        name=ws.name,
        layer=ws.layer,
        true_quality={t: 0.05 for t in ws.true_quality},
        cost_tokens=ws.cost_tokens,
        latency_ms=ws.latency_ms * 3,
        advertised=dict(ws.advertised),
    )
    pool["web_search"] = sab
    if hasattr(router, "layers"):
        for layer_tools in router.layers:
            for i, t in enumerate(layer_tools):
                if t.name == "web_search":
                    layer_tools[i] = sab
    return pool


def run_m65_variant(router_cls, label: str) -> list[dict]:
    """100-query comparison, 5 seeds, shared stream — one router class."""
    queries = generate_queries(np.random.default_rng(QUERY_SEED))
    out = []
    for seed in range(N_SEEDS):
        pool = build_tool_pool()
        router = router_cls(pool)
        rng = np.random.default_rng(seed)
        recs = [router.route(q, rng) for q in queries]
        s = summarize_run(recs)
        s["seed"] = seed
        s["method"] = label
        s["rewards"] = [r.reward for r in recs]
        out.append(s)
    return out


def run_m66_variant(router_cls, label: str) -> list[dict]:
    """Sabotage at query #50; returns per-seed traces + share histories."""
    queries = generate_queries(np.random.default_rng(QUERY_SEED))
    out = []
    for seed in range(N_SEEDS):
        pool = build_tool_pool()
        router = router_cls(pool)
        rng = np.random.default_rng(seed)
        recs = []
        picks_l1 = []
        shares = []
        for i, q in enumerate(queries):
            if i + 1 == SABOTAGE_EVENT:
                pool = _apply_sabotage(pool, router)
            rec = router.route(q, rng)
            recs.append(rec)
            picks_l1.append(rec.path[0])
            window = picks_l1[-10:]
            shares.append(window.count("web_search") / len(window))
        s = summarize_run(recs)
        s["seed"] = seed
        s["method"] = label
        s["rewards"] = [r.reward for r in recs]
        s["rolling_share"] = shares
        s["restarts"] = list(getattr(router, "restarts", []))
        out.append(s)
    return out


def verdict(runs):
    """M6.6 DoD clauses, same operationalization as the committed runner."""
    share_pass = 0
    recovery_pass = 0
    for s in runs:
        shares = s["rolling_share"]
        rewards = s["rewards"]
        pre = np.mean(rewards[20:49])
        target = 0.9 * pre
        post_window = shares[49:79]
        min_share = min(post_window) if post_window else 1.0
        if min_share < 0.20:
            share_pass += 1
        post_rewards = np.array(rewards[59:79])
        if len(post_rewards) >= 10:
            rolling = np.convolve(post_rewards, np.ones(10) / 10, mode="valid")
            if rolling.max() >= target:
                recovery_pass += 1
    return share_pass, recovery_pass


def mean_cum(runs):
    return np.cumsum(np.mean([s["rewards"] for s in runs], axis=0), axis=0)


def main() -> None:
    out_dir = Path("experiments/results/m6-rt")
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir = Path("experiments/results/figures")

    # --- M6.5 re-run: both routers, same stream/seeds ---
    before = run_m65_variant(PheromoneRouter, "as_router")
    after = run_m65_variant(BoundedPheromoneRouter, "mmas_router")

    # --- M6.6 re-run: sabotage, both routers ---
    sab_before = run_m66_variant(PheromoneRouter, "as_router")
    sab_after = run_m66_variant(BoundedPheromoneRouter, "mmas_router")

    sb, rb = verdict(sab_before)
    sa, ra = verdict(sab_after)

    # --- Figure 1: M6.5 before/after convergence ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2), dpi=150)
    xs = np.arange(1, 101)
    for ax, runs, title in (
        (ax1, before, "before: plain router (M6.5 committed behavior)"),
        (ax2, after, "after: bounded router (MMAS bounds + restart)"),
    ):
        cum = mean_cum(runs)
        ax.plot(xs, cum, color="tab:purple", lw=2, label="router")
        ax.axhline(16.88, color="tab:red", ls="--", lw=1, label="greedy-advertised (committed)")
        ax.axhline(36.46, color="k", ls=":", lw=1, label="oracle (committed)")
        ax.set_title(f"{title}\nfinal cumulative {cum[-1]:.2f} (5 seeds)", fontsize=9)
        ax.set_xlabel("query")
        ax.legend(fontsize=7)
        ax.grid(alpha=0.25)
    ax1.set_ylabel("cumulative reward (mean over 5 seeds)")
    fig.tight_layout()
    fig.savefig(fig_dir / "m6rt-comparison.png")
    plt.close(fig)

    # --- Figure 2: M6.6 before/after money plot ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2), dpi=150, sharey=True)
    for ax, runs, title in (
        (ax1, sab_before, f"before: plain router — share {sb}/5, recovery {rb}/5"),
        (ax2, sab_after, f"after: bounded router — share {sa}/5, recovery {ra}/5"),
    ):
        mean_share = np.mean([s["rolling_share"] for s in runs], axis=0)
        ax.plot(xs, mean_share, color="tab:blue", lw=2)
        ax.axvline(SABOTAGE_EVENT, color="red", ls="--", lw=1)
        ax.axhline(0.20, color="grey", ls=":", lw=1)
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("query")
        ax.grid(alpha=0.25)
    ax1.set_ylabel("web_search L1 share (rolling 10, mean over 5 seeds)")
    fig.tight_layout()
    fig.savefig(fig_dir / "m6rt-sabotage.png")
    plt.close(fig)

    summary = {
        "protocol": {
            "n_seeds": N_SEEDS,
            "query_seed": QUERY_SEED,
            "n_queries": 100,
            "sabotage_event": SABOTAGE_EVENT,
            "note": "identical to committed M6.5/M6.6; only the router class changes",
            "router_delta": "MMAS bounds (Q/best, ratio 8) + restart after 20 stagnant queries",
        },
        "comparison": {
            "before_mean_cumulative": float(mean_cum(before)[-1]),
            "after_mean_cumulative": float(mean_cum(after)[-1]),
            "before_mean_reward": float(np.mean([s["mean_reward"] for s in before])),
            "after_mean_reward": float(np.mean([s["mean_reward"] for s in after])),
        },
        "sabotage": {
            "before": {"share_pass": sb, "recovery_pass": rb},
            "after": {"share_pass": sa, "recovery_pass": ra},
            "dod_required": 4,
            "restarts_after": [list(s["restarts"]) for s in sab_after],
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    print(f"\nfigures: {fig_dir / 'm6rt-comparison.png'}, {fig_dir / 'm6rt-sabotage.png'}")


if __name__ == "__main__":
    main()