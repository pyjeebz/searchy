"""One-command generation of the demo-video TSP assets (Act 2).

Implements the demo-video plan (docs/demo-video-script.md): regenerates
the committed Act-2 figures — colony GIF, convergence plot, pheromone
heatmap — from the same seeds as the M4-L table, so the video shows the
numbers the table reports.

CLI::

    uv run python -m searchy.tsp_viz_demo
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from searchy.tsp import load_named
from searchy.tsp_aco import run_as_timed, run_mmas_timed
from searchy.tsp_viz import animate_colony, plot_convergence, plot_tau_heatmap

OUT = Path("experiments/results/figures")


def main() -> None:
    inst = load_named("eil51", "data/tsplib")
    OUT.mkdir(parents=True, exist_ok=True)

    # Colony GIF: light AS run, deterministic seed 0 (video asset).
    gif = animate_colony(
        "eil51",
        "data/tsplib",
        OUT / "tsp-colony.gif",
        seed=0,
        n_ants=20,
        n_iterations=80,
        every=2,
        fps=4,
    )
    print(f"colony GIF: {gif}")

    # Convergence plot: AS vs AS+2opt vs MMAS vs MMAS+2opt, 5 seeds each,
    # shorter horizon than the table (readable on video).
    hist: dict[str, np.ndarray] = {}
    for label, fn, ls in (
        ("AS", run_as_timed, False),
        ("AS+2opt", run_as_timed, True),
        ("MMAS", run_mmas_timed, False),
        ("MMAS+2opt", run_mmas_timed, True),
    ):
        runs = [
            fn(inst.dist, n_ants=inst.n, n_iterations=100, seed=s, local_search=ls)[0]
            for s in range(5)
        ]
        hist[label] = np.stack([r.history_best for r in runs])
    conv = plot_convergence(
        hist,
        inst.known_optimum,
        OUT / "tsp-convergence.png",
        title="eil51: mean best-so-far over 5 seeds (100 iters)",
    )
    print(f"convergence: {conv}")

    # Pheromone heatmap: final tau from an AS+2opt run (the learned graph).
    r, s, snaps = run_as_timed(
        inst.dist,
        n_ants=inst.n,
        n_iterations=100,
        seed=0,
        local_search=True,
        snapshot_iterations=(100,),
    )
    hm = plot_tau_heatmap(
        snaps[100],
        OUT / "tsp-tau-heatmap.png",
        title=f"eil51 pheromone after 100 iters (AS+2opt, best {r.best_length})",
    )
    print(f"heatmap: {hm}")

    # A tiny provenance file so the video's numbers trace to code.
    provenance = {
        "seed": 0,
        "instance": "eil51",
        "colony_gif": {"n_ants": 20, "n_iterations": 80},
        "convergence": {"seeds": list(range(5)), "n_iterations": 100},
        "heatmap_run": {"best_length": int(r.best_length)},
    }
    (OUT / "tsp-video-provenance.json").write_text(json.dumps(provenance, indent=1))
    print(f"provenance: {OUT / 'tsp-video-provenance.json'}")


if __name__ == "__main__":
    main()
