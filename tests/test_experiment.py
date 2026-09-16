"""Tests for the comparison-experiment runner and its metrics/plots.

Implements M6.5 invariants: the DoD verdict logic (both clauses, both
verdicts), the learning-curve smoother's expanding head, run aggregation,
config validation, end-to-end determinism, the shared-stream protocol
(all methods see the identical query sequence), and output artifacts.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from searchy.experiment import (
    GREEDY,
    ORACLE,
    ROUTER,
    compute_verdict,
    load_config,
    main,
    run_experiment,
    write_outputs,
)
from searchy.metrics import path_quality, rolling_mean, summarize_run


# --- unit tests on metrics -------------------------------------------------


def test_rolling_mean_has_expanding_head() -> None:
    """Window 3 over [1,2,3,4]: the first two points average what exists."""
    out = rolling_mean([1.0, 2.0, 3.0, 4.0], window=3)
    assert np.allclose(out, [1.0, 1.5, 2.0, 3.0])


def test_rolling_mean_full_window_is_trailing() -> None:
    out = rolling_mean([0.0, 0.0, 0.0, 9.0], window=2)
    assert np.allclose(out, [0.0, 0.0, 0.0, 4.5])


def _record(reward: float, quality: float) -> SimpleNamespace:
    """Minimal duck-typed record: two layers, same quality, known costs."""
    results = [
        SimpleNamespace(quality=quality, cost_tokens=100, latency_ms=10),
        SimpleNamespace(quality=quality, cost_tokens=200, latency_ms=20),
    ]
    return SimpleNamespace(reward=reward, results=results)


def test_path_quality_multiplies_layer_qualities() -> None:
    assert path_quality(_record(0.0, 0.5)) == pytest.approx(0.25)


def test_summarize_run_aggregates_a_synthetic_run() -> None:
    records = [_record(1.0, 0.5), _record(3.0, 0.1)]
    summary = summarize_run(records)
    assert summary["n_queries"] == 2
    assert summary["cumulative_reward"] == pytest.approx(4.0)
    assert summary["mean_reward"] == pytest.approx(2.0)
    assert summary["mean_quality"] == pytest.approx((0.25 + 0.01) / 2)
    # final window is the whole run here (2 < FINAL_WINDOW)
    assert summary["final_quality"] == pytest.approx(0.13)
    assert summary["mean_cost_tokens"] == pytest.approx(300.0)
    assert summary["mean_latency_ms"] == pytest.approx(30.0)


# --- the DoD verdict logic --------------------------------------------------


def _per_run(cumulative: dict[str, list[float]], mean_rewards: dict[str, float]):
    """Build per_run entries: {method: [cum per seed 0..4]}."""
    per_run = []
    for method, cums in cumulative.items():
        for seed, cum in enumerate(cums):
            per_run.append(
                {
                    "method": method,
                    "seed": seed,
                    "cumulative_reward": cum,
                    "mean_reward": mean_rewards[method],
                }
            )
    return per_run


def test_compute_verdict_rejects_three_of_five_wins() -> None:
    """Router wins seeds 0/2/4 only (3 < 4) and sits at 0.833 of oracle."""
    per_run = _per_run(
        {ROUTER: [10, 9, 8, 7, 6], GREEDY: [9, 10, 7, 8, 5], ORACLE: [0] * 5},
        {ROUTER: 0.5, GREEDY: 0.45, ORACLE: 0.6},
    )
    verdict = compute_verdict(per_run, seeds=[0, 1, 2, 3, 4])
    assert verdict["beats_greedy_advertised"]["wins"] == 3
    assert verdict["beats_greedy_advertised"]["required"] == 4
    assert verdict["beats_greedy_advertised"]["met"] is False
    assert verdict["within_10pct_of_oracle"]["ratio"] == pytest.approx(0.5 / 0.6)
    assert verdict["within_10pct_of_oracle"]["met"] is False
    assert verdict["dod_met"] is False


def test_compute_verdict_passes_when_both_clauses_met() -> None:
    per_run = _per_run(
        {ROUTER: [10] * 5, GREEDY: [9] * 5, ORACLE: [0] * 5},
        {ROUTER: 0.59, GREEDY: 0.45, ORACLE: 0.6},
    )
    verdict = compute_verdict(per_run, seeds=[0, 1, 2, 3, 4])
    assert verdict["beats_greedy_advertised"]["met"] is True
    assert verdict["within_10pct_of_oracle"]["met"] is True
    assert verdict["dod_met"] is True


def test_compute_verdict_nine_tenths_ratio_counts_as_within() -> None:
    """'Within 10%' is inclusive: ratio exactly 0.9 meets the clause."""
    per_run = _per_run(
        {ROUTER: [10] * 5, GREEDY: [9] * 5, ORACLE: [0] * 5},
        {ROUTER: 0.54, GREEDY: 0.45, ORACLE: 0.6},
    )
    verdict = compute_verdict(per_run, seeds=[0, 1, 2, 3, 4])
    assert verdict["within_10pct_of_oracle"]["ratio"] == pytest.approx(0.9)
    assert verdict["within_10pct_of_oracle"]["met"] is True


# --- config / runner / outputs ----------------------------------------------


def test_load_config_rejects_missing_required_keys(tmp_path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("n_per_type: 2\nquery_seed: 0\n")
    with pytest.raises(ValueError, match="missing required keys"):
        load_config(str(path))


def _small_config(tmp_path) -> dict:
    return {
        "name": "test-comparison",
        "n_per_type": 2,  # 8 queries per run
        "query_seed": 100,
        "seeds": [0, 1],
        "methods": [ROUTER, GREEDY, ORACLE],
        "router": {
            "alpha": 1.0,
            "beta": 2.0,
            "rho": 0.05,
            "epsilon": 0.1,
            "q": 1.0,
            "tau0": 1.0,
            "evaporation_batch": 10,
        },
        "rolling_window": 10,
        "output_dir": str(tmp_path / "out"),
        "figure": str(tmp_path / "fig" / "convergence.png"),
    }


def test_run_experiment_is_deterministic_and_shares_the_stream(tmp_path) -> None:
    """Same config twice -> identical rows; and every method sees the same
    query sequence (the honesty rule the whole milestone rests on)."""
    config = _small_config(tmp_path)
    first = run_experiment(config)
    second = run_experiment(config)
    assert first["rows"] == second["rows"]
    assert first["verdict"] == second["verdict"]

    frame = pd.DataFrame(first["rows"])
    for (_, query_index), group in frame.groupby(["seed", "query_index"]):
        assert group["query_type"].nunique() == 1, (
            "methods saw different query types at the same stream position"
        )
    # every (seed, method) ran the full stream
    counts = frame.groupby(["seed", "method"]).size()
    assert (counts == 8).all()


def test_write_outputs_produces_all_artifacts(tmp_path) -> None:
    config = _small_config(tmp_path)
    results = run_experiment(config)
    write_outputs(results)

    records = pd.read_csv(config["output_dir"] + "/records.csv")
    assert len(records) == 2 * 3 * 8  # seeds x methods x queries
    assert set(records["method"]) == {ROUTER, GREEDY, ORACLE}

    per_run = pd.read_csv(config["output_dir"] + "/summary.csv")
    assert len(per_run) == 6

    with open(config["output_dir"] + "/summary.json") as f:
        summary = json.load(f)
    assert summary["protocol"]["query_seed"] == 100
    assert summary["verdict"]["dod_met"] in (True, False)
    assert len(summary["method_means"]) == 3

    figure = __import__("pathlib").Path(config["figure"])
    assert figure.exists() and figure.stat().st_size > 0


def test_main_rejects_bad_usage(capsys) -> None:
    assert main([]) == 2
    assert main(["a", "b"]) == 2
    assert "usage" in capsys.readouterr().err