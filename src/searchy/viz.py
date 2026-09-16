"""Plots for the comparison experiments.

Implements M6.5 (convergence plot). M6.6 will add the sabotage money plot
and GIF; M6.7 the pheromone heatmaps.

Non-interactive Agg backend throughout: figures are written to files,
never shown.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

# One style per method, reused across every M6.x figure for consistency.
METHOD_STYLES: dict[str, dict] = {
    "pheromone_router": {
        "color": "#1f77b4",
        "linewidth": 2.2,
        "label": "ACO router (ours)",
    },
    "greedy-advertised": {
        "color": "#ff7f0e",
        "linewidth": 1.4,
        "label": "greedy-advertised",
    },
    "greedy-cheapest": {
        "color": "#8c564b",
        "linewidth": 1.2,
        "label": "greedy-cheapest",
    },
    "random": {
        "color": "#7f7f7f",
        "linewidth": 1.2,
        "label": "random",
    },
    "oracle": {
        "color": "black",
        "linewidth": 1.4,
        "linestyle": "--",
        "label": "oracle (upper bound)",
    },
}


def convergence_plot(
    curves: dict[str, Sequence[float]],
    router_band: tuple[Sequence[float], Sequence[float]] | None,
    window: int,
    out_path: str,
    title: str = "Searchy M6.5 — learning curves",
) -> None:
    """Mean rolling-reward learning curve per method over the query stream.

    ``curves`` maps method name -> one point per query (already the
    across-seed mean of the rolling-mean reward). ``router_band`` is the
    (min, max) across seeds for the router, drawn as a shaded band so the
    headline method's seed spread is visible.
    """
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = range(1, len(next(iter(curves.values()))) + 1)
    ax.axhline(0.0, color="0.85", linewidth=0.8, zorder=0)  # rewards go negative
    for method, mean in curves.items():
        style = METHOD_STYLES.get(method, {"label": method})
        if method == "pheromone_router" and router_band is not None:
            ax.fill_between(
                x,
                router_band[0],
                router_band[1],
                color=style.get("color", "0.7"),
                alpha=0.18,
                zorder=0,
            )
        ax.plot(x, mean, zorder=2, **style)
    ax.set_xlabel("query index")
    ax.set_ylabel(f"reward (rolling mean, window {window})")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)