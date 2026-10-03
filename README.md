# Searchy — an Ant Colony that Routes Search Traffic, Proven on Real API Fixtures

**The claim, measured:** a pheromone-learning router that picks per-query
tools from *realized rewards alone* — never trusting advertised metadata —
beats random routing on recorded **Firecrawl** fixtures (effective cost
87.5 vs 101.0, p=0.004, 30 seeds) and saves **41%** vs the wrong static
default. On the wrong-config day — the day a source breaks — it reroutes
from experience while static baselines eat the damage forever.

Every number below is measured (seeds + protocol + p-values), every
experiment replays deterministically from committed fixtures, and the
honest negatives are logged, not hidden.

| | Result | Evidence (one command each) |
|---|---|---|
| **Firecrawl overlay** | router beats random routing (p=0.004, n=30); **−41% cost vs wrong static default**; honest loss to the right default on a 25-query stream (D10) | `uv run python -m searchy.fo_experiment` → [`figures/fo-overlay.png`](experiments/results/figures/fo-overlay.png) |
| **Sabotage resilience** (simulated tools, 100 queries × 5 seeds) | colony reroutes off a sabotaged tool from rewards alone (+0.035 vs static −0.129); recovery DoD honestly NOT met — and the MMAS-bounds backport improves recovery 1/5→2/5 (D11) | `uv run python -m searchy.sabotage experiments/configs/m6.6-sabotage.yaml` → [`figures/m6.6-sabotage.png`](experiments/results/figures/m6.6-sabotage.png) |
| **Canonical TSP validation** | AS+2-opt median gaps **0.00/0.00/1.11%** on eil51/berlin52/eil101 (10 seeds, equal budget); 2-opt's gain p<2e-4 everywhere; berlin52 optimum hit on all seeds | `uv run python -m searchy.tsp_experiment experiments/configs/m4l-tsp/eil51-as.yaml` (×12 configs) → [`m4l-tsp/summary.csv`](experiments/results/m4l-tsp/summary.csv) |
| **Proven improvements** | NN-init: eil51 plain-AS gap 6.81%→5.52% (p=0.04). Candidate lists: **−44% construction time** at equal quality. Combined variant: buys nothing (D12) | `uv run python -m searchy.m7_experiment nn_init` → [`m7-nn_init/summary.json`](experiments/results/m7-nn_init/summary.json) |

## The 2-minute tour

1. **The router learns routing from traffic.** Each query is an "ant"
   walking two tool layers (retrieve → process) with the ACO transition
   rule τ^α·η^β; good paths deposit pheromone, evaporation forgets.
   Two tool advertisements deliberately lie — the colony must learn to
   distrust them. `src/searchy/router.py`
2. **It survives sabotage.** At query #50 the best tool's quality drops
   95%, latency triples. Static baselines never adapt; the colony moves
   traffic within 30 queries. The honest story (D5): adaptation is real
   but plateaus — the exact failure MMAS bounds fix.
   `docs/demo-script.md`, `figures/m6.6-sabotage.gif`
3. **The mechanism is validated where ground truth exists.** Same
   algorithm on TSPLIB: one 12-config grid, 3 instances × 10 seeds × 4
   methods, Wilcoxon p-values, byte-identical one-command repro.
   `experiments/results/m4l-tsp/`
4. **Then it spends real credits, deliberately.** 76 live Firecrawl
   calls recorded ONCE (~$1.8, human-approved), committed as an auditable
   fixture set — every experiment replays free, forever, deterministically.
   `experiments/fixtures/firecrawl-overlay.jsonl`,
   `docs/firecrawl-overlay.md`

## Why this repo reads as product engineering

- **Fixture-first honesty:** live API calls happen exactly once, with
  approval, and are logged to diffable JSONL; every reported number
  replays. Reproducibility is a command, not a promise.
- **Honest negatives are the record:** D1–D12 in
  `docs/diagnosis-log.md` — including two reward-scale defects caught by
  mechanism audits, an ablation that exposed a missing exponent, and
  negative results reported at full protocol strength.
- **Stats discipline:** every comparison carries seeds, equal-budget
  protocol, and a tie-corrected Wilcoxon (validated against scipy to
  1e-5).

## The honest negatives (headline ones)

- The router **loses to the right static default** on a 25-query overlay
  stream — exploration can't amortize that fast (D10).
- The sabotage recovery DoD is **not met** at committed parameters
  (D5), and the MMAS-bounds backport is a Pareto move, not a strict win
  (D11).
- The TSP improvement grid: mostly washes under 2-opt (D12) — which is
  itself the finding: *refinement matters more than variant choice*.

## Layout

```
src/searchy/          router (ACO core), bounded router, tools, queries,
                      reward, baselines, TSP loaders/solvers, experiment
                      runners (M6.x / M4-L / M7 / M6-RT / FO), viz
experiments/configs/  one YAML per experiment (one command each)
experiments/results/  CSV + JSON summaries + figures/ (all committed)
experiments/fixtures/ the recorded Firecrawl evidence (76 calls, 72 credits)
docs/                 primer, design doc, diagnosis log D1–D12, overlay
                      doc, demo script, video script
blog/posts/           stubs (human writes)
data/tsplib/          eil51, berlin52, eil101 (canonical instances)
tests/                164 tests, all passing
```

## Dev setup

```bash
uv sync
uv run pytest          # 164 passed
```

Firecrawl replay needs no API key (fixtures committed). Live recording
is a single approved pass: `uv run python -m searchy.fo_record`.

## Project plan

`ROADMAP.md` (charter v2+v3, single source of truth) ·
`PROGRESS.md` (every milestone, every verdict) ·
`CLAUDE.md` (conventions: measured claims only, fixture-first,
honest negatives logged).