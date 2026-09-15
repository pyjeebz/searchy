# ROADMAP — ACO Demo-First: "Searchy" Agent → Research → Proven Improvements

This is the project charter, verbatim. It is the single source of truth.
Milestones are worked strictly in order; after each milestone: update
`PROGRESS.md`, commit, tag, stop for human review.

## Working rules
1. Never skip ahead. Complete the current milestone, show results, wait for
   my go-ahead.
2. I (the human) own: reading milestones (R-items) and blog writing (M8).
   You own: all code, experiments, scaffolding docs. Never block on my items.
3. Update PROGRESS.md after every milestone. One git commit per milestone,
   tagged (r0.1, m6.1, ...).
4. When something behaves strangely in experiments, log it in
   docs/diagnosis-log.md — these observations drive my reading and the blog.
   Flag them to me explicitly; do not silently patch them away.
5. Honest results only. A negative result that's well-measured beats a fudged win.

## Mission
1. STAGE 1: Build "Searchy" — a search agent that routes queries through a
   simulated tool pool using ant colony optimization (pheromone learning).
2. STAGE 2: I read the ACO literature as *diagnosis* of what we observed.
3. STAGE 3: Verify claims on the canonical TSP with controlled benchmarks.
4. STAGE 4: Prove improvements (on TSP, and backported to Searchy).
5. Publish 5 blog posts in demo-first order (plan at bottom).

## Conventions
See `CLAUDE.md` (Python 3.11+, uv, CPU-only, NumPy-first, explicit
`np.random.Generator` everywhere, milestone IDs in docstrings, YAML-config
experiments, pytest for the listed invariants).

## STAGE 1 — Primer + Build (Weeks 1–3)

### R0.1 — ACO crash primer doc (docs/primer.md)
Content, exactly these five things, no more:
1. Stigmergy in one paragraph (indirect coordination via environment).
2. The transition rule the router will use:
   P(tool_j | layer l, query q) ∝ τ[l][j]^α · η[j,q]^β
   where η[j,q] = each tool's *advertised* (noisy, possibly wrong) skill match.
3. The pheromone update, applied per query batch:
   τ ← (1 − ρ)·τ  then  τ[l][j] += Q · R(path) for every edge the query used
4. Exploration safeguard: with probability ε pick a uniform random tool.
5. A mapping table: ACO concept → Searchy equivalent
   (ants→queries, graph→tool layers, τ→tool preferences, η→advertised skills,
   evaporation→forgetting stale tool quality, deposit→rewarding good paths).
Start params: α=1, β=2, ρ=0.05, ε=0.1, Q=1, reward-weighted deposit.
Gate (human must pass before coding starts): can write the transition rule and
update equation from memory.

### M6.1 — Design doc (docs/design-searchy.md)
Spec the system (adapt details if there's a problem — but justify).
DoD: doc approved by human. Then commit, tag m6.1.

### M6.2 — queries.py + tools.py
100 synthetic queries, 4 types × 25; 6 simulated tools in 2 layers; true
quality profiles designed so the best tool differs by type; advertised
η = true + seeded noise, misleading by design on 1–2 tools.
DoD: generate the 100 queries deterministically under seed; call any tool on
any query returns stable (quality, cost, latency); tests pass.

### M6.3 — router.py (the ACO core)
Each query is an "ant" walking layer1 → layer2. τ is a per-layer 3-vector,
persisted across queries. Deposit weighted by that query's reward; evaporation
per batch of 10 queries.
DoD: routes a query through both layers; τ persists and changes across 100
queries; probability rows sum to 1; tests pass.

### M6.4 — baselines.py
(1) random tools; (2) greedy-cheapest; (3) greedy-advertised (max η, no
learning); (4) ORACLE = brute-force best path per query type (upper bound).
DoD: all four baselines produce (path, quality, cost, latency) for every
query; oracle values precomputable per type.

### M6.5 — Comparison experiment
Config: 100 queries × 5 seeds, all methods, same query stream.
Metrics: cumulative reward, final mean quality, mean cost, learning curve.
DoD: pheromone router beats greedy-advertised on cumulative reward on ≥4/5
seeds and lands within 10% of ORACLE's mean utility — or we get a measured
negative result + diagnosis-log entry. Convergence plot produced.

### M6.6 — Sabotage demo (the flagship moment)
At query #50: web_search true quality drops to 0.05 AND latency ×3.
DoD: on ≥4/5 seeds, web_search's Layer-1 traffic share falls below 20%
within 30 queries of the event, mean utility recovers to ≥90% of its
pre-sabotage rolling average, and we produce the money plot: per-tool traffic
share over query index, with a vertical line at #50. Save as PNG + GIF.

### M6.7 — Pheromone heatmaps
DoD: τ heatmaps per layer at queries 25 / 50 / 75 / 100, split by query type;
math queries visibly route differently from factual queries. Save PNGs.

**GATE 1 (end of Stage 1):** 2-minute narratable demo + all artifacts.

## STAGE 2 — Diagnosis-driven reading (Weeks 3–5) — HUMAN OWNS
Maintained in PROGRESS.md, never done by the agent. Each item: trigger →
reading → deliverable (which blog section it unlocks).
- R1.1 | trigger: router stagnation/recovery observed | read: Dorigo & Stützle
  ch.1–2 (or Scholarpedia) | unlock: Post 2 mechanics section
- R1.2 | trigger: comparing our loop to the original | read: Dorigo/Maniezzo/
  Colorni 1996 (Ant System) | unlock: Post 2 "vs the original" section
- R2.1 | trigger: τ collapse or over-dominance seen | read: Stützle & Hoos
  2000 (MAX-MIN AS) | unlock: Post 3 section on pheromone bounds
- R2.2 | trigger: exploitation questions | read: Dorigo & Gambardella 1997
  (ACS) | unlock: Post 3 section on q0/exploitation
- R2.3 | deliverable: variants comparison table (AS/ACS/MMAS × 6 attributes)
  framed as "fixes to bugs we saw" | unlock: Post 3 centerpiece
- R3.1 | read: AMRO-S + ACO-ToT (skim) | unlock: Post 2 sidebar
- R3.2 | read: DyNACO anti-stagnation idea | unlock: Post 5 improvement idea

## STAGE 3 — Canonical test: TSP (Weeks 5–7)
- M0.2/M0.3: TSPLIB loader (EUC_2D) + nearest-neighbor baseline.
  Sanity: eil51 NN ≈ 426±15%, berlin52 opt 7542, eil101 opt 629.
- M3.1: AS from scratch on eil51 — median gap <8% over 10 seeds.
- M3.2: convergence GIF + pheromone heatmap.
- M3.3: logging harness (best/mean/diversity per iteration → CSV → plots).
- M3.4: ACS — beats our AS median on eil51.
- M3.5: MMAS + restarts — no stagnation across 500 iterations
  (diversity ≠ 0 for 50 consecutive iterations).
- M3.6: 2-opt refinement; measure its runtime share (benchmark honesty).
- M4.1–M4.3: experiment runner (one command: config × instances × 30 seeds),
  metrics (gap %, mean±std, time-to-target), Wilcoxon rank-sum + p-values.
- M4.4: baseline study table: AS vs ACS vs MMAS ± 2-opt, 5 TSPLIB instances
  × 30 seeds, equal construction budget. GATE: one-command reproduction.

## STAGE 4 — Improvements, proven (Weeks 7–9)
- M7.1: NN-tour pheromone initialization vs uniform τ0 (5 instances × 30 seeds).
- M7.2: stagnation-triggered restart OR adaptive ρ (same protocol).
- M7.3: candidate lists k=20 on largest instance (quality + runtime).
- M7.4: combined "improved AS" vs vanilla AS and MMAS+2-opt; final table
  with p-values. GATE: defensible claim "X improved Y by Z% (p<0.05, n=30)".
- M7.5: honest negative-results log.
- M6-RT (the payoff): backport MMAS-style pheromone bounds + restart to the
  Searchy router; re-run M6.5/M6.6; measure whether resilience improves
  (recovery speed after sabotage). DoD: before/after comparison plots.

## STAGE 5 — Blog arc (human writes; agent scaffolds blog/posts/*.md)
1. post-1 (~W3): "I Built a Search Agent That Routes Like an Ant Colony"
2. post-2 (~W4–5): "How ACO Actually Works — Explained by a System I Built First"
3. post-3 (~W6): "Everything I Got Wrong, the Literature Knew by 2000"
4. post-4 (~W8): "Does ACO Hold Up on the Traveling Salesman Problem? A Controlled Study"
5. post-5 (~W10): "Can You Improve Ant Colony Optimization? I Ran 30 Seeds (Twice)"