"""Plots for the lean TSP validation sprint (M4-L / minimal viz).

Implements the ROADMAP's "minimal viz" scope: one convergence plot, one
pheromone heatmap — plus the colony-on-the-map animation used by the
demo video. Non-interactive Agg backend: figures are written to files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

import matplotlib

matplotlib.use("Agg")

import matplotlib.animation as animation
import matplotlib.pyplot as plt

from searchy.tsp import load_named, tour_length
from searchy.tsp_aco import run_as_timed


def plot_convergence(
    histories: dict[str, np.ndarray],
    known_optimum: int,
    out_path: str | Path,
    *,
    title: str = "",
    smooth: int = 10,
) -> Path:
    """Mean best-so-far curves per method, one panel.

    ``histories`` maps method label -> array of per-seed history_best rows
    (shape n_seeds x n_iterations); the plot shows the across-seed mean.
    The optimum is a flat reference line.
    """
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=150)
    for label, arr in histories.items():
        arr = np.asarray(arr, dtype=float)
        mean = arr.mean(axis=0)
        if smooth > 1:
            kernel = np.ones(smooth) / smooth
            mean = np.convolve(mean, kernel, mode="valid")
            xs = np.arange(smooth - 1, len(mean) + smooth - 1)
        else:
            xs = np.arange(len(mean))
        ax.plot(xs, mean, label=label, lw=1.8)
    ax.axhline(known_optimum, color="k", ls="--", lw=1.0, alpha=0.7,
               label=f"optimum ({known_optimum})")
    ax.set_xlabel("iteration")
    ax.set_ylabel("best tour length (mean over seeds)")
    if title:
        ax.set_title(title)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p)
    plt.close(fig)
    return p


def plot_tau_heatmap(
    tau: np.ndarray,
    out_path: str | Path,
    *,
    title: str = "",
    coords: np.ndarray | None = None,
) -> Path:
    """Pheromone matrix as a heatmap; optionally overlay the best tour.

    ``tau`` is the snapshot captured by run_*_timed (post-update). Edges
    with more pheromone are brighter — the colony's learned structure.
    """
    fig, ax = plt.subplots(figsize=(5.5, 5.0), dpi=150)
    im = ax.imshow(tau, cmap="viridis", interpolation="nearest")
    fig.colorbar(im, ax=ax, label="tau", shrink=0.85)
    ax.set_xlabel("city j")
    ax.set_ylabel("city i")
    if title:
        ax.set_title(title, fontsize=10)
    fig.tight_layout()
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p)
    plt.close(fig)
    return p


def animate_colony(
    instance_name: str,
    data_dir: str | Path,
    out_path: str | Path,
    *,
    seed: int = 0,
    n_ants: int = 20,
    n_iterations: int = 60,
    every: int = 2,
    fps: int = 4,
) -> Path:
    """The demo-video asset: ants constructing tours on the city map.

    Re-runs a short AS with ``local_search=False`` and per-iteration
    snapshots (light: 20 ants, 60 iterations), drawing every ``every``-th
    iteration: faint grey lines for the current iteration's tours, bold
    gold for the best-so-far tour, cities as points. Deterministic given
    ``seed``. Saved as an animated GIF.
    """
    inst = load_named(instance_name, data_dir)
    snapshots: dict[int, np.ndarray] = {}
    # We need per-iteration tours for the animation; run a light AS and
    # capture histories by re-running with the snapshot mechanism on tau
    # only is not enough — so we rebuild the loop here minimally, reusing
    # the solver's own construction (single source of truth for the
    # transition rule stays in tsp_aco).
    from searchy.tsp_aco import (
        ALPHA,
        BETA,
        Q_DEPOSIT,
        TAU0,
        RHO_AS,
        _construct_tour,
        _eta_matrix,
    )

    rng = np.random.default_rng(seed)
    n = inst.n
    tau = np.full((n, n), float(TAU0))
    np.fill_diagonal(tau, 0.0)
    eta = _eta_matrix(inst.dist)
    best_tour: np.ndarray | None = None
    best_len = int(np.iinfo(np.int64).max)
    frames: list[tuple[np.ndarray, np.ndarray]] = []

    for it in range(n_iterations):
        tours = [
            _construct_tour(inst.dist, eta, tau, rng, ALPHA, BETA)
            for _ in range(n_ants)
        ]
        lengths = np.array([tour_length(t, inst.dist) for t in tours])
        k = int(np.argmin(lengths))
        if lengths[k] < best_len:
            best_len = int(lengths[k])
            best_tour = tours[k].copy()
        if it % every == 0:
            frames.append((np.array(tours), best_tour.copy()))
        tau *= 1.0 - RHO_AS
        for t, l in zip(tours, lengths):
            dep = Q_DEPOSIT / l
            edges = np.stack([t, np.roll(t, -1)])
            tau[edges[0], edges[1]] += dep
            tau[edges[1], edges[0]] += dep

    fig, ax = plt.subplots(figsize=(6, 5.5), dpi=110)
    xs, ys = inst.coords[:, 0], inst.coords[:, 1]

    def draw(frame_idx: int) -> None:
        ax.clear()
        tours, bt = frames[frame_idx]
        for t in tours:
            pts = inst.coords[t]
            ax.plot(pts[:, 0], pts[:, 1], color="grey", alpha=0.10, lw=0.7)
        bpts = inst.coords[bt]
        ax.plot(bpts[:, 0], bpts[:, 1], color="goldenrod", lw=2.2, alpha=0.95)
        ax.scatter(xs, ys, s=14, c="k", zorder=3)
        ax.set_title(
            f"{instance_name}: iter {frame_idx * every}, best {best_len}"
        )
        ax.set_xticks([])
        ax.set_yticks([])

    ani = animation.FuncAnimation(
        fig, draw, frames=len(frames), interval=1000 // fps
    )
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ani.save(p, writer="pillow", fps=fps)
    plt.close(fig)
    return p