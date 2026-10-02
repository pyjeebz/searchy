# Searchy — A Demo-First Ant Colony Optimization Project

A ~10-week solo project: build a search agent ("Searchy") that routes queries
through a simulated tool pool using ant colony optimization (pheromone
learning), *then* read the ACO literature as diagnosis of what was observed,
verify claims on canonical TSP benchmarks, prove improvements, and publish 5
blog posts in demo-first order.

- **Plan, status, conventions, and docs:** live in this repo — `ROADMAP.md`
  (charter, single source of truth), `PROGRESS.md`, `CLAUDE.md`,
  `docs/` (primer, design doc, diagnosis log), `blog/posts/` (stubs).

## Layout
```
src/searchy/        queries, tools, router (ACO core), reward, baselines,
                    experiment runners, metrics, viz
experiments/configs/  experiment YAML configs
experiments/results/  CSV + JSON results, figures/ subfolder
tests/              pytest suites
data/               TSPLIB instances etc.
```

## Dev setup
```bash
uv sync
uv run pytest
```