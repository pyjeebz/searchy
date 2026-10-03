# ROADMAP — ACO Demo-First: "Searchy" Agent → Research → Proven Improvements

This is the project charter (v1, amended by v2 and v3 — see changelog at
bottom). It is the single source of truth. Milestones are worked strictly in
order; after each milestone: update `PROGRESS.md`, commit, tag, stop for human
review.

## Working rules
1. Never skip ahead. Complete the current milestone, show results, wait for
   my go-ahead.
2. I (the human) own: reading milestones (R-items), blog writing (Stage 5),
   and Track B. You own: all code, experiments, scaffolding docs. Never
   block on my items.
3. Update PROGRESS.md after every milestone. One git commit per milestone,
   tagged (r0.1, m6.1, ...).
4. When something behaves strangely in experiments, log it in
   the diagnosis log (Notion; locally docs/diagnosis-log.md) — these
   observations drive my reading and the blog.
   Flag them to me explicitly; do not silently patch them away.
5. Honest results only. A negative result that's well-measured beats a fudged win.

## Non-negotiable framing rules (charter v2)
1. Claims must be measured: seeds, baselines, p-values — no vibes.
2. Everything Firecrawl-facing is framed as credit/cost savings or quality
   gains on their real API — product language.
3. Reproducibility: all experiments run on recorded fixtures. Live API
   calls ONLY when recording a new fixture set, and only with the human's
   explicit approval (they cost credits).

## Mission
1. STAGE 1: Build "Searchy" — a search agent that routes queries through a
   simulated tool pool using ant colony optimization (pheromone learning).
2. STAGE 2: I read the ACO literature as *diagnosis* of what we observed
   (trimmed to 4 core items, charter v2).
3. STAGE 3: LEAN VALIDATION SPRINT on canonical TSP (~1 week, agent-built):
   the statistics harness we reuse later + Post 4 material. NOT a full
   variant tour.
4. STAGE 4: Improvements, proven (M7.1–M7.5 + M6-RT backport to Searchy).
5. STAGE 5 (FO): Firecrawl Overlay module — timeboxed to ~2 days, after
   Stage 4, human credit approval required.
6. Publish 5 blog posts in demo-first order (plan at bottom). Track B runs
   in parallel (human-owned).

## Conventions
See `CLAUDE.md` (Python 3.11+, uv, CPU-only, NumPy-first, explicit
`np.random.Generator` everywhere, milestone IDs in docstrings, YAML-config
experiments, pytest for the listed invariants).

## STAGE 1 — Primer + Build (Weeks 1–3)

### R0.1 — ACO crash primer doc (Notion; locally docs/primer.md)
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

### M6.1 — Design doc (Notion; locally docs/design-searchy.md)
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

**GATE 1 (G6, end of Stage 1):** 2-minute narratable demo + all artifacts.

## STAGE 2 — Diagnosis-driven reading (Weeks 3–5) — HUMAN OWNS
Trimmed to 4 core items (charter v2). Maintained in PROGRESS.md, never done
by the agent. Each item: trigger → reading → deliverable (which blog section
it unlocks).
- R1.1 | trigger: router stagnation/recovery observed | read: Dorigo & Stützle
  ch.1–2 (or Scholarpedia) | unlock: Post 2 mechanics section
- R2.1 | trigger: τ collapse or over-dominance seen | read: Stützle & Hoos
  2000 (MAX-MIN AS) | unlock: Post 3 section on pheromone bounds (MMAS as
  the fix to the bug we observed — D3/D4/D5)
- R2.3 | deliverable: variants comparison table (AS/ACS/MMAS × 6 attributes)
  framed as "fixes to bugs we saw" | unlock: Post 3 centerpiece
- R3.1 | read: AMRO-S + ACO-ToT (skim) | unlock: Post 2 sidebar (honest
  similarities AND differences)

Optional backlog (trimmed in charter v2 for Firecrawl focus):
- R1.2 (Dorigo/Maniezzo/Colorni 1996), R2.2 (ACS q0/exploitation), R3.2
  (DyNACO anti-stagnation) — revisit only if a milestone demands them.

## STAGE 3 — Lean TSP validation sprint (Week 5, ~1 week, agent-built)
Purpose: build the statistics harness we reuse for later evals + produce
Post 4 material. NOT a full variant tour.
- M0.2/M0.3: TSPLIB loader (EUC_2D: eil51, berlin52, eil101) + NN baseline.
  Sanity: eil51 NN ≈ 426±15%, berlin52 opt 7542, eil101 opt 629.
- M3.1: AS from scratch on eil51 — median gap <8% over 10 seeds.
- M3.5: MMAS + restarts — no stagnation across 500 iterations
  (diversity ≠ 0 for 50 consecutive iterations).
- M3.6: 2-opt refinement; measure its runtime share (benchmark honesty).
- M4-L: experiment runner + metrics + Wilcoxon rank-sum p-values → ONE
  table: AS vs MMAS ± 2-opt, 3 instances × 30 seeds, equal construction
  budget. GATE: one-command reproducibility.
- Minimal viz: one convergence plot + one pheromone heatmap (from M3.2's
  scope, trimmed).
- DROPPED (charter v2): ACS (M3.4), 5th instance, candidate lists. Absorbed
  into Stage 4 where they serve the claim — "M-FC owned improvements" is
  void under v3; Stage 4 (M7.x) owns improvements now.

## STAGE 4 — Improvements, proven (Weeks 6–8)
- M7.1: NN-tour pheromone initialization vs uniform τ0 (3 instances × 30
  seeds).
- M7.2: stagnation restart OR adaptive ρ (same protocol).
- M7.3: candidate lists k=20 on largest instance (quality + runtime).
- M7.4: combined "improved AS" vs vanilla AS and MMAS+2-opt; final table
  with p-values. GATE: defensible claim "X improved Y by Z% (p<0.05, n=30)".
- M7.5: honest negative-results log.
- M6-RT (the payoff): backport MMAS-style pheromone bounds + restart to the
  Searchy router; re-run M6.5/M6.6; measure whether resilience improves
  (recovery speed after sabotage). DoD: before/after comparison plots.

## STAGE 5 — Firecrawl Overlay (FO) (after Stage 4, ~2 days timeboxed)
Human credit approval REQUIRED before FO.1. Rule: if FO scope grows beyond
2 days, cut it — the overlay DOC matters more than the overlay DEMO.
- FO.1 | Fixture record: ~25 queries × 5 Firecrawl tool calls (/search,
  /map, /scrape markdown, /scrape json/product) recorded ONCE (≤$15
  credits) → fixture set; router then runs the stream from fixtures with
  30 seeds like any experiment (deterministic, cheap).
- FO.2 | Overlay demo plot: traffic share + cumulative credit spend over
  the query stream, incl. one adaptation moment (degrade one domain in
  fixtures). One figure. Do not let this balloon.
- FO.3 | overlay doc (Notion; locally docs/firecrawl-overlay.md): the mapping table — ACO mechanism →
  Firecrawl search problem → what I'd do differently at their scale.
  Interview prep + application attachment.

## STAGE 6 — Blog arc (human writes; lives in Notion — blog/ untracked)
1. post-1 (~W3): "I Built a Search Agent That Routes Like an Ant Colony"
2. post-2 (~W4): "How ACO Actually Works — Explained by a System I Built
   First" (R1.1, R3.1)
3. post-3 (~W5): "Everything I Got Wrong, the Literature Knew by 2000"
   (R2.1, R2.3)
4. post-4 (~W6): "I Benchmarked My Colony on the Classic Problem" — lean TSP
   study; shorter post, stats discipline on display
5. post-5 (~W8): "Can You Improve ACO? I Ran 30 Seeds to Find Out" (M7 +
   M6-RT + R3.2). Optional Post 6 / final section of Post 5: the Firecrawl
   overlay demo.
Outreach can start at Post 1 regardless.

## TRACK B — visibility track (parallel, capped at 2–3h/week, HUMAN OWNS)
- TB.1: be usefully active in Firecrawl's Discord.
- TB.2: 1–2 small merged PRs to github.com/firecrawl/firecrawl (docs, SDK
  fixes, or an examples/ contribution — read CONTRIBUTING.md).
- TB.3: when Post 1 ships, share it publicly and tag them appropriately.

## Changelog
- v1: original charter (Stage 1 build → reading → full TSP tour →
  improvements → 5 posts).
- v2 (Firecrawl calibration): project reframed as hiring asset; framing
  rules (measured claims, product language, fixture reproducibility);
  Session 0 re-baseline; Stage 2 trimmed to R1.1/R2.1/R2.3/R3.1 (R1.2,
  R2.2, R3.2 → optional backlog); Stage 3 → lean validation sprint (drop
  ACS, 5th instance, candidate lists); Stage 4 → flagship M-FC
  (credit-aware router on live fixtures); Track B added; blog arc revised.
- v3 (overlay strategy, self-contained project): DELETE the M-FC stage
  entirely; RESTORE v1's Stage 3 TSP at v2's lean scope and Stage 4
  improvements (M7.1–M7.5 + M6-RT backport); KEEP v2's Session 0 re-baseline,
  trimmed reading, Track B; ADD the Firecrawl Overlay module (FO.1–FO.3,
  ~2 days, credit approval required, doc > demo); Post 5 restored to "Can
  You Improve ACO? I Ran 30 Seeds to Find Out" (M7 + M6-RT + R3.2), with
  optional Post 6 / Post 5 final section for the overlay demo; planning docs
  back in-repo (self-contained project), Notion no longer the home of
  record.