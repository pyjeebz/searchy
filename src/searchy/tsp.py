"""TSPLIB instance loading and tour length for the Stage 3 validation sprint.

Implements M0.2 (TSPLIB loader, EUC_2D) and the tour-length convention every
Stage 3 experiment shares.

TSPLIB EUC_2D semantics (Reinelt 1991): edge weights are Euclidean distances
rounded to the nearest integer — ``nint(sqrt(dx^2 + dy^2) + 0.5)`` — NOT
plain floats. Getting this wrong shifts eil51's optimum by ~0.4%, so the
rounding is the loader's core contract and is tested directly.

Instances live in ``data/tsplib/`` (eil51, berlin52, eil101 — downloaded
verbatim from a TSPLIB mirror; see PROGRESS.md M0.2 entry). Known optima
are published constants, not parsed from anywhere.

Pure parsing: no randomness, so no generator is needed here. Sampling
solvers (AS/MMAS/NN start cities) take the caller's ``np.random.Generator``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Known optimal tour lengths (TSPLIB documentation; rounded EUC_2D weights).
KNOWN_OPTIMA: dict[str, int] = {
    "eil51": 426,
    "berlin52": 7542,
    "eil101": 629,
}

# Stage 3 instances, per charter v2/v3 (lean sprint: 3 instances).
STAGE3_INSTANCES: tuple[str, ...] = ("eil51", "berlin52", "eil101")

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "tsplib"


@dataclass(frozen=True)
class TSPInstance:
    """One TSPLIB EUC_2D instance: coordinates + its integer distance matrix."""

    name: str
    coords: np.ndarray  # (n, 2) float coordinates as parsed
    dist: np.ndarray  # (n, n) int32 TSPLIB-rounded Euclidean distances
    known_optimum: int | None  # published optimum, if we track the instance

    @property
    def n(self) -> int:
        return len(self.coords)


def _parse_euc2d(text: str, name: str) -> tuple[np.ndarray, int]:
    """Parse DIMENSION and the NODE_COORD_SECTION of a TSPLIB EUC_2D file."""
    lines = text.splitlines()
    dimension: int | None = None
    edge_weight_type: str | None = None
    coord_lines: list[str] = []
    in_coords = False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if in_coords:
            if upper.startswith("EOF"):
                break
            coord_lines.append(line)
            continue
        if upper.startswith("DIMENSION"):
            dimension = int(line.split(":")[1])
        elif upper.startswith("EDGE_WEIGHT_TYPE"):
            edge_weight_type = line.split(":")[1].strip()
        elif upper.startswith("NODE_COORD_SECTION"):
            in_coords = True
    if dimension is None:
        raise ValueError(f"{name}: no DIMENSION")
    if edge_weight_type != "EUC_2D":
        raise ValueError(f"{name}: EDGE_WEIGHT_TYPE {edge_weight_type!r} != EUC_2D")
    if len(coord_lines) != dimension:
        raise ValueError(f"{name}: expected {dimension} coords, got {len(coord_lines)}")
    rows = np.array([[float(x) for x in c.split()] for c in coord_lines])
    indices = rows[:, 0].astype(int)
    expected = np.arange(1, dimension + 1)
    if not np.array_equal(indices, expected):
        raise ValueError(f"{name}: node indices are not 1..{dimension} in order")
    return rows[:, 1:3], dimension


def load_instance(path: str | Path) -> TSPInstance:
    """Load a TSPLIB EUC_2D instance from ``path`` (coordinates + distances).

    Distances follow TSPLIB's rounded-Euclidean convention (Reinelt):
    d(i,j) = nint(sqrt(dx^2+dy^2) + 0.5), i.e. floor(d + 0.5). The diagonal
    is 0 and the matrix is symmetric by construction.
    """
    p = Path(path)
    name = p.stem
    text = p.read_text()
    coords, dimension = _parse_euc2d(text, name)
    diff = coords[:, None, :] - coords[None, :, :]
    euclid = np.sqrt((diff**2).sum(axis=-1))
    dist = np.floor(euclid + 0.5).astype(np.int32)
    np.fill_diagonal(dist, 0)
    return TSPInstance(
        name=name,
        coords=coords,
        dist=dist,
        known_optimum=KNOWN_OPTIMA.get(name),
    )


def instance_path(name: str, data_dir: str | Path = _DATA_DIR) -> Path:
    """Canonical path of a shipped instance file in ``data_dir``."""
    return Path(data_dir) / f"{name}.tsp"


def load_named(name: str, data_dir: str | Path = _DATA_DIR) -> TSPInstance:
    """Load one of the shipped instances by name (e.g. ``"eil51"``)."""
    if name not in KNOWN_OPTIMA:
        raise ValueError(f"unknown instance {name!r}; known: {sorted(KNOWN_OPTIMA)}")
    return load_instance(instance_path(name, data_dir))


def tour_length(tour: np.ndarray, dist: np.ndarray) -> int:
    """Length of a tour given as a permutation of node indices (0-based).

    The tour is cyclic: the last node connects back to the first. Accepts
    any 1-D integer array covering every node exactly once.
    """
    tour = np.asarray(tour)
    n = dist.shape[0]
    if tour.ndim != 1 or len(tour) != n:
        raise ValueError(f"tour must be a length-{n} permutation, got shape {tour.shape}")
    if len(np.unique(tour)) != n:
        raise ValueError("tour must visit every node exactly once")
    d = np.asarray(dist)
    return int(d[tour, np.roll(tour, -1)].sum())


def gap_percent(length: int, known_optimum: int) -> float:
    """Excess over the published optimum, in percent."""
    if known_optimum <= 0:
        raise ValueError("known_optimum must be positive")
    return 100.0 * (length - known_optimum) / known_optimum


def nearest_neighbor_tour(
    dist: np.ndarray, start: int, rng: np.random.Generator | None = None
) -> np.ndarray:
    """Greedy nearest-neighbor tour starting at ``start`` (0-based).

    Implements M0.3. Deterministic given ``start``; ``rng`` is accepted for
    uniformity with the sampling solvers but unused — NN makes no random
    choices. (Stage 3 protocol: report NN over all n start cities, or a
    seeded subset when n is large; see the runner.)
    """
    n = dist.shape[0]
    if not 0 <= start < n:
        raise ValueError(f"start {start} out of range for n={n}")
    tour = np.empty(n, dtype=np.int64)
    tour[0] = start
    visited = np.zeros(n, dtype=bool)
    visited[start] = True
    current = start
    for k in range(1, n):
        d = dist[current].copy()
        d[visited] = np.iinfo(np.int32).max
        nxt = int(np.argmin(d))
        tour[k] = nxt
        visited[nxt] = True
        current = nxt
    return tour

def two_opt(tour: np.ndarray, dist: np.ndarray) -> np.ndarray:
    """First-improvement 2-opt on ``tour`` until no improving move exists.

    Implements M3.6 (local refinement; runtime share is measured by the
    callers, who time construction vs refinement separately). A 2-opt move
    replaces edges (a,b) and (c,d) with (a,c) and (b,d) by reversing a
    tour segment; the gain is d(a,b)+d(c,d) − d(a,c) − d(b,d). Deterministic:
    scans i,j in index order, takes the first positive-gain move, repeats.
    Returns the improved tour; the input is never modified.
    """
    t = np.asarray(tour).copy()
    n = len(t)
    d = np.asarray(dist)
    improved = True
    while improved:
        improved = False
        for i in range(n - 1):
            a, b = t[i], t[(i + 1) % n]
            # j > i+1 in segment order; vectorized gain over all j at once
            js = np.arange(i + 2, n if i > 0 else n - 1)
            if len(js) == 0:
                continue
            cs = t[js]
            ds = t[(js + 1) % n]
            gain = int(d[a, b]) + d[cs, ds] - d[a, cs] - d[b, ds]
            k = int(np.argmax(gain > 0))
            if gain[k] > 0:
                j = int(js[k])
                t[i + 1 : j + 1] = t[i + 1 : j + 1][::-1]
                improved = True
                break
    return t
