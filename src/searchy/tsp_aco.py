"""ACO solvers for symmetric TSP — the Stage 3 canonical test.

Implements M3.1 (AS from scratch) and M3.5 (MMAS + stagnation restart);
Dorigo/Maniezzo/Colorni 1996 and Stützle/Hoos 2000 as wired into this
project's conventions — the M4-L comparison table measures them against
each other, and M6-RT backports the MMAS bounds to the Searchy router.

The loop mirrors the Searchy router's ACO shape on a real graph: every
iteration, m ants each construct one tour with the transition rule

    P(j | i) ∝ tau[i,j]**alpha * eta[i,j]**beta,  eta[i,j] = 1/d(i,j)

over unvisited cities (η = 1/d is the standard TSP heuristic; distances
are the loader's TSPLIB-rounded integers, η is float). After all ants
finish, one evaporation + one deposit round:

    tau <- (1 - rho) * tau
    tau[i,j] += Q / L_k   for every edge of ant k's tour (all m ants)

AS (M3.1) deposits all m ants' tours and leaves τ unbounded — the exact
weakness D3/D5 showed in Searchy. MMAS (M3.5) changes only the deposit
target (iteration-best only) and clamps τ into [tau_min, tau_max] with
Stützle & Hoos's (1/best_length)-scaled bounds; when no improvement is
seen for ``stagnation_threshold`` consecutive iterations, τ is reset to
tau_max (the literature's restart) — the anti-stagnation mechanism the
Searchy backport wants. All sampling flows through the caller's
``np.random.Generator``; same seed ⇒ identical run, byte-for-byte.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from searchy.tsp import tour_length

# Shared construction-rule parameters (standard literature settings for
# TSP; kept verbatim, never tuned per-instance — see M4-L's protocol).
ALPHA = 1.0  # pheromone weight
BETA = 5.0  # heuristic weight (1/d)
Q_DEPOSIT = 100.0  # deposit scale; deposits are Q / L
TAU0 = 1e-6  # AS initial pheromone (small, deposits dominate early)

# AS-specific.
RHO_AS = 0.5  # AS evaporation per iteration

# MMAS-specific (Stützle & Hoos 2000 defaults for TSP).
RHO_MMAS = 0.02  # MMAS evaporation per iteration
MMAS_TAU_MAX_FACTOR = 1.0  # tau_max = factor / best_length
MMAS_TAU_MIN_FACTOR = 0.001  # tau_min = factor * n * tau_max... see bounds()
STAGNATION_THRESHOLD = 50  # no-improvement iterations before restart
MMAS_TAU0_MODE = "max"  # initial τ: start at tau_max (asymptotic MMAS)


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


def canonical_tour(tour: np.ndarray) -> tuple[int, ...]:
    """A tour's canonical form: (direction, rotation)-invariant key.

    A TSP tour and its reverse cover the same edges; so does any rotation
    of the cycle. Canonicalizing to (min node first, lexicographically
    smaller direction) makes distinct-edge-set comparisons honest — the
    diversity metric counts different TOURS, not different orderings.
    """
    t = [int(x) for x in tour]
    n = len(t)
    i0 = t.index(min(t))
    forward = t[i0:] + t[:i0]
    backward = [forward[0]] + list(reversed(forward[1:]))
    return tuple(min(forward, backward))


def tour_diversity(tours: list[np.ndarray]) -> int:
    """Number of distinct tours among ``tours`` (canonicalized).

    The M3.5 stagnation observable: if all m ants build the same tour,
    diversity is 1 and the colony has stopped exploring — the TSP image
    of D3/D5's lock-in.
    """
    return len({canonical_tour(t) for t in tours})


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


def _eta_matrix(dist: np.ndarray) -> np.ndarray:
    """Heuristic matrix η = 1/d (0 on diagonal and degenerate 0-edges)."""
    with np.errstate(divide="ignore"):
        eta = np.where(dist > 0, 1.0 / np.maximum(dist, 1), 0.0)
    np.fill_diagonal(eta, 0.0)
    return eta


def run_as(
    dist: np.ndarray,
    n_ants: int,
    n_iterations: int,
    seed: int,
    *,
    alpha: float = ALPHA,
    beta: float = BETA,
    rho: float = RHO_AS,
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
    eta = _eta_matrix(dist)

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


@dataclass(frozen=True)
class MMASResult(ASResult):
    """MMAS run record: everything AS tracks, plus the stagnation story.

    ``history_diversity`` is the per-iteration count of distinct (canon-
    icalized) tours built by the m ants; ``restarts`` is the list of
    1-based iterations at which τ was reset to tau_max; ``tau_min`` /
    ``tau_max`` are the run's (dynamic) bounds actually used.
    """

    history_diversity: np.ndarray
    restarts: tuple[int, ...]
    tau_min: float
    tau_max: float


def _mmas_bounds(
    n: int, best_length: int, tau_max_factor: float, tau_min_factor: float
) -> tuple[float, float]:
    """Stützle & Hoos's dynamic bounds given the current best tour length.

    tau_max = tau_max_factor / best_length  (asymptote as rho->0 phrasing)
    tau_min = tau_min_factor * n * tau_max  (their ratio-of-extremes rule;
    the factor here is chosen as the standard "avg vs best" separation so
    a single tau_min_factor parameter controls how strongly MMAS forces
    exploration. With factor 0.001 on eil51: tau_min ≈ 1.2e-5·tau_max.)
    """
    tau_max = tau_max_factor / float(best_length)
    tau_min = tau_min_factor * n * tau_max
    return tau_min, tau_max


def run_mmas(
    dist: np.ndarray,
    n_ants: int,
    n_iterations: int,
    seed: int,
    *,
    alpha: float = ALPHA,
    beta: float = BETA,
    rho: float = RHO_MMAS,
    q: float = Q_DEPOSIT,
    tau_max_factor: float = MMAS_TAU_MAX_FACTOR,
    tau_min_factor: float = MMAS_TAU_MIN_FACTOR,
    stagnation_threshold: int = STAGNATION_THRESHOLD,
    restart_tau_mode: str = MMAS_TAU0_MODE,
    rng: np.random.Generator | None = None,
) -> MMASResult:
    """Run MAX-MIN Ant System with stagnation restarts on ``dist``.

    MMAS differs from AS in exactly three ways (Stützle & Hoos 2000):
    (1) only the iteration-best ant deposits (we use iteration-best, the
    paper's default; global-best-only stagnates harder);
    (2) τ is clamped to [tau_min, tau_max] after every update, with
    bounds recomputed from the current best length (they tighten as the
    best improves);
    (3) when no new best for ``stagnation_threshold`` consecutive
    iterations, τ is reset to tau_max everywhere (the paper's restart) —
    exploration re-seeds from scratch while the best tour is remembered.

    Determinism: same seed + same arguments ⇒ identical MMASResult.
    """
    if rng is None:
        rng = np.random.default_rng(seed)
    n = dist.shape[0]
    eta = _eta_matrix(dist)
    # Warm-start bound with the greedy NN length so tau_max is finite
    # before any tour exists (standard practice: initial bounds from a
    # constructive heuristic).
    from searchy.tsp import nearest_neighbor_tour

    warm = min(
        tour_length(nearest_neighbor_tour(dist, start=s), dist)
        for s in range(min(n, 10))
    )
    tau_min, tau_max = _mmas_bounds(
        n, warm, tau_max_factor, tau_min_factor
    )
    if restart_tau_mode == "max":
        tau = np.full((n, n), tau_max)
    else:
        tau = np.full((n, n), tau_min)
    np.fill_diagonal(tau, 0.0)

    best_tour: np.ndarray | None = None
    best_length = np.iinfo(np.int64).max
    best_iteration = 0
    history_best = np.empty(n_iterations, dtype=np.int64)
    history_mean = np.empty(n_iterations, dtype=np.float64)
    history_diversity = np.empty(n_iterations, dtype=np.int64)
    restarts: list[int] = []
    since_improvement = 0

    for it in range(n_iterations):
        tours = [
            _construct_tour(dist, eta, tau, rng, alpha, beta)
            for _ in range(n_ants)
        ]
        lengths = np.array([tour_length(t, dist) for t in tours])
        history_mean[it] = lengths.mean()
        history_diversity[it] = tour_diversity(tours)
        it_best = int(np.argmin(lengths))
        if lengths[it_best] < best_length:
            best_length = int(lengths[it_best])
            best_tour = tours[it_best].copy()
            best_iteration = it + 1
            tau_min, tau_max = _mmas_bounds(
                n, best_length, tau_max_factor, tau_min_factor
            )
            since_improvement = 0
        else:
            since_improvement += 1
        history_best[it] = best_length

        tau *= 1.0 - rho
        t = tours[it_best]
        deposit = q / float(lengths[it_best])
        edges = np.stack([t, np.roll(t, -1)])
        tau[edges[0], edges[1]] += deposit
        tau[edges[1], edges[0]] += deposit

        if since_improvement >= stagnation_threshold:
            tau = np.full((n, n), tau_max)
            np.fill_diagonal(tau, 0.0)
            restarts.append(it + 1)
            since_improvement = 0
        else:
            np.clip(tau, tau_min, tau_max, out=tau)
            np.fill_diagonal(tau, 0.0)

    assert best_tour is not None
    return MMASResult(
        best_tour=best_tour,
        best_length=best_length,
        best_iteration=best_iteration,
        history_best=history_best,
        history_mean=history_mean,
        n_ants=n_ants,
        n_iterations=n_iterations,
        history_diversity=history_diversity,
        restarts=tuple(restarts),
        tau_min=tau_min,
        tau_max=tau_max,
    )