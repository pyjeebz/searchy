"""Tests for the M4-L runner and the Wilcoxon harness.

Implements M4-L test coverage: p-value correctness on hand-checkable
cases, runner protocol invariants (equal budget, all methods present,
summary/table shape), and viz asset generation.
"""

from __future__ import annotations

import numpy as np
import pytest
import yaml
from pathlib import Path

from searchy.metrics import rank_sum_pvalue
from searchy.tsp import load_named
from searchy.tsp_viz import animate_colony, plot_convergence, plot_tau_heatmap


# --- Wilcoxon rank-sum (M4-L stats harness) ---


def test_pvalue_disjoint_small_samples():
    # a=[1,2,3] vs b=[4,5,6]: U=0; two-sided normal-approx p ~ 0.0495
    p = rank_sum_pvalue([1, 2, 3], [4, 5, 6])
    assert 0.03 < p < 0.08


def test_pvalue_identical_samples_is_one():
    assert rank_sum_pvalue([5, 5, 5], [5, 5, 5]) == 1.0


def test_pvalue_symmetric_in_argument_order():
    a = [3, 1, 4, 1, 5, 9, 2, 6]
    b = [2, 7, 1, 8, 2, 8]
    assert rank_sum_pvalue(a, b) == rank_sum_pvalue(b, a)


def test_pvalue_shifted_n30_is_tiny():
    rng = np.random.default_rng(0)
    p = rank_sum_pvalue(rng.normal(0, 1, 30), rng.normal(5, 1, 30))
    assert p < 1e-6


def test_pvalue_rejects_empty():
    with pytest.raises(ValueError):
        rank_sum_pvalue([], [1.0])


def test_pvalue_handles_integer_ties():
    rng = np.random.default_rng(1)
    a = rng.integers(420, 500, 30)
    b = a + rng.integers(-10, 11, 30)
    p = rank_sum_pvalue(a, b)
    assert 0.0 <= p <= 1.0


# --- runner protocol (micro config, tmp dirs) ---


@pytest.fixture(scope="module")
def micro_summary(tmp_path_factory):
    from searchy.tsp_experiment import run_experiment

    d = tmp_path_factory.mktemp("m4l")
    cfg = {
        "name": "micro",
        "instances": ["eil51"],
        "seeds": [0, 1],
        "n_ants": "n",
        "n_iterations": 5,
        "data_dir": "data/tsplib",
        "output_dir": str(d / "out"),
        "figure_dir": str(d / "figs"),
    }
    cfg_path = d / "micro.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))
    return run_experiment(cfg_path), d


def test_micro_run_all_methods_all_seeds(micro_summary):
    import pandas as pd

    summary, d = micro_summary
    df = pd.read_csv(d / "out" / "runs.csv")
    assert set(df.method) == {"AS", "AS+2opt", "MMAS", "MMAS+2opt"}
    assert len(df) == 1 * 2 * 4
    assert set(df.seed) == {0, 1}


def test_micro_summary_rows_and_pvalues(micro_summary):
    import pandas as pd

    summary, d = micro_summary
    df = pd.read_csv(d / "out" / "summary.csv")
    method_rows = df[~df.method.str.startswith("p[")]
    assert len(method_rows) == 4
    p_rows = df[df.method.str.startswith("p[")]
    assert len(p_rows) == 4
    assert (p_rows.mean_gap_percent >= 0).all()
    assert (p_rows.mean_gap_percent <= 1).all()


def test_micro_ls_only_for_2opt_variants(micro_summary):
    import pandas as pd

    summary, d = micro_summary
    df = pd.read_csv(d / "out" / "runs.csv")
    assert (df[df.method == "AS"].ls_s == 0).all()
    assert (df[df.method == "AS+2opt"].ls_s > 0).all()
    assert (df[df.method == "MMAS"].ls_s == 0).all()
    assert (df[df.method == "MMAS+2opt"].ls_s > 0).all()


def test_protocol_recorded_in_summary(micro_summary):
    summary, d = micro_summary
    proto = summary["protocol"]
    assert proto["equal_construction_budget"] is True
    assert proto["n_seeds"] == 2
    assert "Wilcoxon" in proto["stats"]


# --- viz assets (tiny instances only; smoke) ---


def test_plot_convergence_and_heatmap(tmp_path):
    from searchy.tsp_aco import run_as_timed

    inst = load_named("eil51", "data/tsplib")
    r, s, snaps = run_as_timed(
        inst.dist, n_ants=5, n_iterations=8, seed=0, snapshot_iterations=(8,)
    )
    p1 = plot_convergence(
        {"AS": r.history_best.reshape(1, -1)}, inst.known_optimum,
        tmp_path / "conv.png",
    )
    assert p1.stat().st_size > 0
    p2 = plot_tau_heatmap(snaps[8], tmp_path / "tau.png")
    assert p2.stat().st_size > 0


def test_animate_colony_writes_gif(tmp_path):
    p = animate_colony(
        "eil51", "data/tsplib", tmp_path / "colony.gif",
        seed=0, n_ants=5, n_iterations=6, every=2, fps=2,
    )
    assert p.stat().st_size > 0
