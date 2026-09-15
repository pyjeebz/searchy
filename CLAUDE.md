# CLAUDE.md — Project Conventions (Searchy / ACO Demo-First)

## What this is
A ~10-week solo demo-first ACO project. Stage 1 builds "Searchy" (a search agent
routing queries through a simulated tool pool via pheromone learning), then the
human reads the ACO literature as *diagnosis* of observed behavior, claims are
verified on canonical TSP benchmarks, and improvements are proven and backported.
The full milestone plan lives in `ROADMAP.md` — that file is the single source
of truth. Progress tracking lives in `PROGRESS.md`.

## Ownership (critical)
- **Agent owns:** all code, experiments, scaffolding docs (primer, design doc).
- **Human owns:** all reading milestones (R-items) and all blog *writing* (M8).
  Never block on human-owned items, never do them.
- One milestone at a time. After completing a milestone: update `PROGRESS.md`,
  commit, tag (`r0.1`, `m6.1`, ...), show results, **stop and wait for review**.
- Anything strange observed in experiments goes in `docs/diagnosis-log.md`,
  AND is explicitly flagged to the human. Never silently patch weirdness away.
- Honest results only. A well-measured negative result beats a fudged win.

## Technical conventions
- **Python 3.11+, uv, CPU-only, NumPy-first.** No ML frameworks.
- **Determinism:** explicit `np.random.Generator` threaded through every
  function that samples. Same seed ⇒ identical results. **No global random
  state** — never call `np.random.*` legacy functions or `random.*` module
  functions without a passed generator.
- **Module style:** small flat modules; plain functions/classes with type
  hints; every docstring cites its milestone ID (e.g. `Implements M6.3`).
- **Experiments:** YAML configs in `experiments/configs/` → results CSV + JSON
  in `experiments/results/` → figures in `experiments/results/figures/`.
- **Tests (pytest):** router probability rows sum to 1; pheromone persistence
  across queries; tool/query determinism under fixed seed; baseline correctness.
- **Style:** readable > clever. No premature abstraction. Match the
  surrounding code's density and naming.

## Experiment honesty rules
- Every reported number comes with seeds count and protocol (equal budget,
  same query stream / tour constructions for all methods compared).
- Negative results get logged, not hidden.
- Runtime is measured and attributed when it matters (e.g. 2-opt share in M3.6).