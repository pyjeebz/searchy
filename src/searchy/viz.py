"""Plots for the comparison experiments.

Implements M6.5 (convergence plot), M6.6 (the sabotage money plot, static
PNG + animated GIF), and M6.7 (the pheromone heatmap panels).

Non-interactive Agg backend throughout: figures are written to files,
never shown.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402

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


# Layer-1 tools get their own colors so the money plot can show per-tool
# curves; the sabotage target gets the alarm red.
_TOOL_COLORS: dict[str, str] = {
    "web_search": "#d62728",
    "knowledge_base": "#2ca02c",
    "vector_db": "#9467bd",
}


def _draw_money(
    ax_share,
    ax_reward,
    *,
    router_shares: dict[str, Sequence[float]],
    share_band: tuple[Sequence[float], Sequence[float]] | None,
    contrast_shares: dict[str, Sequence[float]],
    reward_curves: dict[str, Sequence[float]],
    reward_band: tuple[Sequence[float], Sequence[float]] | None,
    window: int,
    event_query: int,
    share_threshold: float,
    sabotaged_tool: str,
    upto: int,
    n_total: int,
    event_shown: bool,
    title: str,
) -> None:
    """(Re)draw both money-plot panels showing the first ``upto`` queries.

    Top: Layer-1 traffic share per tool (router mean + seed band for the
    sabotaged tool) with the never-adapting greedy and instantly-adapting
    oracle shown on the sabotaged tool only. Bottom: rolling reward per
    method. One frame of the GIF is exactly one call of this function.
    """
    ax_share.clear()
    ax_reward.clear()
    x = range(1, upto + 1)

    # --- top panel: per-tool Layer-1 traffic share -------------------------
    ax_share.set_ylim(0.0, 1.0)
    ax_share.axhline(
        share_threshold,
        color="0.6",
        linewidth=0.9,
        linestyle=":",
        label=f"DoD: below {share_threshold:.0%}",
        zorder=0,
    )
    if share_band is not None:
        ax_share.fill_between(
            x,
            share_band[0][:upto],
            share_band[1][:upto],
            color=_TOOL_COLORS.get(sabotaged_tool, "0.7"),
            alpha=0.15,
            zorder=0,
            linewidth=0,
        )
    for name, curve in router_shares.items():
        targeted = name == sabotaged_tool
        ax_share.plot(
            x,
            curve[:upto],
            color=_TOOL_COLORS.get(name, "0.45"),
            linewidth=2.4 if targeted else 1.5,
            label=name + (" (sabotaged)" if targeted else ""),
            zorder=3 if targeted else 2,
        )
    for method, curve in contrast_shares.items():
        style = METHOD_STYLES.get(method, {})
        ax_share.plot(
            x,
            curve[:upto],
            color=style.get("color", "0.4"),
            linewidth=1.2,
            linestyle="--",
            alpha=0.9,
            label=f"{method}: {sabotaged_tool} share",
            zorder=1,
        )
    ax_share.set_ylabel(f"Layer-1 traffic share (rolling, window {window})")

    # --- bottom panel: rolling reward per method ---------------------------
    ax_reward.axhline(0.0, color="0.85", linewidth=0.8, zorder=0)
    if reward_band is not None:
        ax_reward.fill_between(
            x,
            reward_band[0][:upto],
            reward_band[1][:upto],
            color=METHOD_STYLES.get("pheromone_router", {}).get("color", "0.7"),
            alpha=0.18,
            zorder=0,
            linewidth=0,
        )
    for method, curve in reward_curves.items():
        style = METHOD_STYLES.get(method, {"label": method})
        ax_reward.plot(x, curve[:upto], zorder=2, **style)
    ax_reward.set_ylabel(f"reward (rolling mean, window {window})")
    ax_reward.set_xlabel("query index")

    # --- the event marker, once it has happened ---------------------------
    if event_shown:
        ax_share.axvline(
            event_query,
            color=_TOOL_COLORS.get(sabotaged_tool, "0.4"),
            alpha=0.6,
            linewidth=1.4,
            label=f"{sabotaged_tool} sabotaged (#{event_query})",
            zorder=0,
        )
        ax_reward.axvline(event_query, color="0.4", alpha=0.5, linewidth=1.2, zorder=0)

    for ax in (ax_share, ax_reward):
        ax.set_xlim(1, n_total)
    ax_share.set_title(title)
    ax_share.legend(loc="upper right", fontsize=7.5, ncol=2)
    ax_reward.legend(loc="best", fontsize=8)


def _money_data_len(curves: dict[str, Sequence[float]]) -> int:
    return len(next(iter(curves.values())))


def money_plot(
    router_shares: dict[str, Sequence[float]],
    share_band: tuple[Sequence[float], Sequence[float]] | None,
    contrast_shares: dict[str, Sequence[float]],
    reward_curves: dict[str, Sequence[float]],
    reward_band: tuple[Sequence[float], Sequence[float]] | None,
    *,
    window: int,
    event_query: int,
    share_threshold: float,
    sabotaged_tool: str,
    out_path: str,
    title: str,
) -> None:
    """The M6.6 money plot: traffic share and reward around the sabotage.

    ``router_shares`` maps Layer-1 tool name -> rolling share curve
    (across-seed mean), ``share_band`` the router's across-seed (min, max)
    for the sabotaged tool, ``contrast_shares`` method name -> the
    sabotaged tool's share for greedy/oracle, ``reward_curves`` method ->
    rolling-mean reward (across-seed mean) with ``reward_band`` for the
    router.
    """
    fig, (ax_share, ax_reward) = plt.subplots(2, 1, figsize=(8.5, 8.0), sharex=True)
    n_total = _money_data_len(router_shares)
    _draw_money(
        ax_share,
        ax_reward,
        router_shares=router_shares,
        share_band=share_band,
        contrast_shares=contrast_shares,
        reward_curves=reward_curves,
        reward_band=reward_band,
        window=window,
        event_query=event_query,
        share_threshold=share_threshold,
        sabotaged_tool=sabotaged_tool,
        upto=n_total,
        n_total=n_total,
        event_shown=True,
        title=title,
    )
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def money_gif(
    router_shares: dict[str, Sequence[float]],
    share_band: tuple[Sequence[float], Sequence[float]] | None,
    contrast_shares: dict[str, Sequence[float]],
    reward_curves: dict[str, Sequence[float]],
    reward_band: tuple[Sequence[float], Sequence[float]] | None,
    *,
    window: int,
    event_query: int,
    share_threshold: float,
    sabotaged_tool: str,
    out_path: str,
    title: str,
    fps: int = 10,
) -> None:
    """Animated money plot: one frame per query, event line at its firing.

    Same data as :func:`money_plot`; the x-axis is pinned to the full
    stream so the animation reads as the run unfolding, and the sabotage
    line appears exactly when the event query arrives.
    """
    fig, (ax_share, ax_reward) = plt.subplots(2, 1, figsize=(8.5, 8.0), sharex=True)
    n_total = _money_data_len(router_shares)

    def draw_frame(upto: int) -> list:
        _draw_money(
            ax_share,
            ax_reward,
            router_shares=router_shares,
            share_band=share_band,
            contrast_shares=contrast_shares,
            reward_curves=reward_curves,
            reward_band=reward_band,
            window=window,
            event_query=event_query,
            share_threshold=share_threshold,
            sabotaged_tool=sabotaged_tool,
            upto=upto,
            n_total=n_total,
            event_shown=upto >= event_query,
            title=title,
        )
        return []

    animation = FuncAnimation(
        fig, draw_frame, frames=range(1, n_total + 1), blit=False
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    animation.save(out_path, writer=PillowWriter(fps=fps), dpi=100)
    plt.close(fig)


def heatmap_panels(
    panels: Sequence[tuple[str, np.ndarray]],
    row_labels: Sequence[str],
    col_labels: Sequence[str],
    *,
    out_path: str,
    title: str,
    value_label: str,
    ncols: int = 2,
    vmin: float | None = None,
    vmax: float | None = None,
    fmt: str = "{:.2f}",
    cmap: str = "viridis",
) -> None:
    """A grid of annotated heatmaps sharing one colorbar (M6.7).

    ``panels`` is a sequence of (panel title, 2-D matrix) pairs, drawn left
    to right / top to bottom. NaN cells are masked and drawn as an em dash.
    ``vmin``/``vmax`` default to the shared data range so every panel is
    comparable at a glance; pass them explicitly to pin a known range.
    """
    matrices = [np.asarray(matrix, dtype=float) for _, matrix in panels]
    n_panels = len(panels)
    ncols = max(1, min(ncols, n_panels))
    nrows = (n_panels + ncols - 1) // ncols

    finite = [matrix[~np.isnan(matrix)] for matrix in matrices if np.isfinite(matrix).any()]
    data_lo = float(min(values.min() for values in finite)) if finite else 0.0
    data_hi = float(max(values.max() for values in finite)) if finite else 1.0
    lo = data_lo if vmin is None else vmin
    hi = data_hi if vmax is None else vmax
    span = (hi - lo) or 1.0

    panel_size = (3.2, 2.8)
    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(panel_size[0] * ncols + 1.4, panel_size[1] * nrows + 1.1),
        squeeze=False,
    )
    images = []
    for ax, (panel_title, matrix) in zip(axes.ravel(), panels):
        data = np.ma.masked_invalid(matrix)
        images.append(ax.imshow(data, cmap=cmap, vmin=lo, vmax=hi, aspect="auto"))
        ax.set_xticks(range(len(col_labels)))
        ax.set_xticklabels(col_labels, fontsize=8, rotation=20, ha="right")
        ax.set_yticks(range(len(row_labels)))
        ax.set_yticklabels(row_labels, fontsize=8)
        ax.set_title(panel_title, fontsize=10)
        for row_index, row in enumerate(data):
            for col_index, value in enumerate(row):
                if np.ma.is_masked(value):
                    text, color = "—", "0.5"
                else:
                    value = float(value)
                    text = fmt.format(value)
                    # white text on the dark end of viridis, black on bright
                    color = "black" if (value - lo) / span > 0.55 else "white"
                ax.text(
                    col_index, row_index, text,
                    ha="center", va="center", fontsize=8, color=color,
                )
    for ax in axes.ravel()[n_panels:]:
        ax.set_visible(False)

    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    # colorbar after layout: a bar spanning all axes is incompatible with
    # tight_layout and would trigger a UserWarning if created first
    colorbar = fig.colorbar(images[0], ax=axes.ravel().tolist(), fraction=0.045, pad=0.02)
    colorbar.set_label(value_label, fontsize=9)
    fig.suptitle(title, fontsize=12)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)