"""Ant System (AS) solver for symmetric TSP — the Stage 3 canonical test.

Implements M3.1 (AS from scratch; Dorigo/Maniezzo/Colorni 1996 as wired into
this project's conventions — the M4-L comparison table will measure it
against MMAS).

The loop mirrors the Searchy router's ACO shape on a real graph: every
iteration, m ants each construct one tour with the transition rule

    P(j | i) ∝ tau[i,j]**alpha * eta[i,j]**beta,  eta[i,j] = 1/d(i,j)

over unvisited cities (η = 1/d is the standard TSP heuristic; distances
are the loader's TSPLIB-rounded integers, η is float). After all ants
finish, one evaporation + one deposit round:

    tau <- (1 - rho) * tau
    tau[i,j] += Q / L_k   for every edge of ant k's tour (all m ants)

This is plain AS: all ants deposit (not elitist/best-only), τ is unbounded
(the exact weakness D3/D5 showed in Searchy — MMAS bounds arrive in M3.5).
All sampling flows through the caller's ``np.random.Generator``; same seed
⇒ identical run, byte-for-byte.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from searchy.tsp import tour_length

# AS starting parameters (Dorigo & Stützle ch.3, parameter-setting table —
# the "standard" AS settings, kept verbatim and never tuned per-instance).
ALPHA = 1.0  # pheromone weight
BETA = 5.0  # heuristic weight (1/d) — standard AS setting for TSP
RHO = 0.5  # evaporation per iteration
Q_DEPOSIT = 100.0  # deposit scale; AS classic: Q / L (tour-length-scaled)
TAU0 = 1e-6  # initial pheromone (small, so deposits dominate early)


@dataclass(frozen=True)
class ASResult:
    """One full AS run's record: best/mean per iteration + the best tour."""

    best_tour: np.ndarray
    best_length: int
    best_iteration: int  # 1-based iteration where the best was found
    history_best: np.ndarray  # best-so-far after each iteration (len n_iter)
    history_mean: np.ndarray  # iteration-mean tour length of the m ants
    n_ants: int
    n_iterations: int


def _construct_tour(
    dist: np.ndarray,
    eta: np.ndarray,
    tau: np.ndarray,
    rng: np.random.Generator,
    alpha: float,
    beta: float,
) -> np.ndarray:
    """One ant's tour: roulette-wheel AS transitions over unvisited cities."""
    n = dist.shape[0]
    tour = np.empty(n, dtype=np.int64)
    current = int(rng.integers(n))
    tour[0] = current
    visited = np.zeros(n, dtype=bool)
    visited[current] = True
    for k in range(1, n):
        scores = tau[current] ** alpha * eta[current] ** beta
        scores[visited] = 0.0
        r = scores.sum()
        if r <= 0.0:
            # Numerical hygiene (mirrors the router): unvisited but all
            # mass zero — fall back to uniform over unvisited.
            choices = np.flatnonzero(~visited)
            nxt = int(choices[rng.integers(len(choices))])
        else:
            nxt = int(rng.choice(n, p=scores / r))
        tour[k] = nxt
        visited[nxt] = True
        current = nxt
    return tour


def run_as(
    dist: np.ndarray,
    n_ants: int,
    n_iterations: int,
    seed: int,
    *,
    alpha: float = ALPHA,
    beta: float = BETA,
    rho: float = RHO,
    q: float = Q_DEPOSIT,
    tau0: float = TAU0,
    rng: np.random.Generator | None = None,
) -> ASResult:
    """Run Ant System for ``n_iterations`` on ``dist``.

    Same seed + same arguments ⇒ identical ASResult (tours, lengths,
    histories). ``rng`` overrides ``seed`` when passed explicitly.
    """
    if rng is None:
        rng = np.random.default_rng(seed)
    n = dist.shape[0]
    tau = np.full((n, n), float(tau0))
    np.fill_diagonal(tau, 0.0)
    with np.errstate(divide="ignore"):
        eta = np.where(dist > 0, 1.0 / np.maximum(dist, 1), 0.0)
    np.fill_diagonal(eta, 0.0)

    best_tour: np.ndarray | None = None
    best_length = np.iinfo(np.int64).max
    best_iteration = 0
    history_best = np.empty(n_iterations, dtype=np.int64)
    history_mean = np.empty(n_iterations, dtype=np.float64)

    for it in range(n_iterations):
        tours = [
            _construct_tour(dist, eta, tau, rng, alpha, beta)
            for _ in range(n_ants)
        ]
        lengths = np.array([tour_length(t, dist) for t in tours])
        history_mean[it] = lengths.mean()
        it_best = int(np.argmin(lengths))
        if lengths[it_best] < best_length:
            best_length = int(lengths[it_best])
            best_tour = tours[it_best].copy()
            best_iteration = it + 1
        history_best[it] = best_length

        tau *= 1.0 - rho
        for t, l in zip(tours, lengths):
            deposit = q / l
            edges = np.stack([t, np.roll(t, -1)])
            tau[edges[0], edges[1]] += deposit
            tau[edges[1], edges[0]] += deposit

    assert best_tour is not None
    return ASResult(
        best_tour=best_tour,
        best_length=best_length,
        best_iteration=best_iteration,
        history_best=history_best,
        history_mean=history_mean,
        n_ants=n_ants,
        n_iterations=n_iterations,
    )