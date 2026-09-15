# M6.1 — Design Doc: "Searchy", a pheromone-learning search agent

Implements M6.1. Spec for M6.2–M6.7 modules. **Status: DRAFT — awaiting
human approval before any src/ code is written.**

## System in one paragraph

A stream of synthetic queries ("ants") each walks a fixed 2-layer tool pool:
one tool in layer 1 ("retrieve"), one in layer 2 ("process"). Tool choice per
layer is stochastic, from the ACO transition rule `P ∝ τ^α · η^β` plus an
ε-random safeguard. After each query, its realized reward (path quality minus
cost/latency penalty) is deposited on the tools it used; every batch of 10
queries the whole matrix evaporates. The colony must learn, from experience
alone, which tools are actually good for which query type — because two tools
*advertise* skills they don't have — and must re-learn when a good tool is
sabotaged mid-stream.

## Module specs

### queries.py (M6.2)
- `generate_queries(rng, n_per_type=25)` → list of `Query`.
- 4 types × 25 = 100 queries: `factual-lookup`, `math-calculation`,
  `text-summarization`, `code-snippet`.
- Each `Query` has: `type` (enum/str), `payload` (synthetic string, e.g.
  `"compute 47*19+3"`, `"who is the 14th element in the periodic table"`).
- Generated from the passed `np.random.Generator`; same seed ⇒ same 100
  queries, same order.

### tools.py (M6.2)
- 6 tools, 2 layers:
  - Layer 1 "retrieve": `web_search`, `vector_db`, `knowledge_base`
  - Layer 2 "process": `small_llm`, `calculator`, `regex_processor`
- Each tool has a **true** quality profile `q(tool|type) ∈ [0,1]`, a token
  **cost**, and a **latency** (ms). Profiles designed so the best tool
  differs per type:

| tool | factual | math | summarization | code |
|---|---|---|---|---|
| web_search   | **0.95** | 0.25 | 0.55 | 0.60 |
| vector_db    | 0.70 | 0.30 | 0.75 | 0.65 |
| knowledge_base | 0.80 | 0.35 | 0.50 | 0.40 |
| small_llm    | 0.60 | 0.55 | **0.95** | **0.85** |
| calculator   | 0.10 | **0.98** | 0.05 | 0.20 |
| regex_processor | 0.20 | 0.40 | 0.30 | 0.70 |

  Costs/latencies (design targets): cheap tools ~200–500 tokens / 50–150 ms;
  `web_search` ~1500 tokens / 800 ms; `small_llm` ~3000 tokens / 1200 ms.
  Exact numbers finalized in M6.2; principle: good-for-type ≠ cheap, so
  router faces real trade-offs.
- `advertised(tool|type) = q(tool|type) + seeded_noise` per (tool, type),
  clipped to [0.05, 1]. **Deliberately misleading on 1–2 (tool, type)
  pairs**: e.g. `knowledge_base` advertises ~0.9 for `math` (true 0.35) and
  `vector_db` advertises ~0.85 for `factual` (true 0.70). These are the
  "ads" the colony must learn to distrust.
- `call(tool, query, rng)` → `(quality, cost, latency)`, where
  `quality = q(tool|type) + per-call seeded noise (σ=0.05, clipped [0,1])`.
  Deterministic given (tool, query, seed). Sabotage (M6.6) is a runtime
  mutation of web_search's true profile: quality→0.05, latency×3, from
  query #50 on.

### router.py (M6.3)
- `PheromoneRouter(n_layers=2, tools_per_layer=3, params, rng)`.
- τ: one row per layer (2×3), initialized uniform (e.g. τ0=1.0), persisted
  across queries within a run.
- Per query: for each layer, with probability ε pick uniform random tool,
  else sample from `softmax-like` transition `τ^α · η^β` (η = advertised
  match for this query's type).
- Evaporation `τ ← (1−ρ)·τ` every 10 queries; deposit
  `τ[l][j] += Q · R(path)` immediately after each query for the two tools
  used.
- Exposes: probability rows (must sum to 1), τ snapshot history.

### reward.py (M6.1)
```
R(path) = product of tool qualities along path
          − λ · (total_cost/1e4 + total_latency/1e3),  λ = 1
```
- `total_cost` = sum of the two tools' token costs; `total_latency` likewise.
- Note: R can be negative (cost penalty can exceed quality). See risk R2
  below for the deposit-clipping decision.

### baselines.py (M6.4)
1. **random** — uniform random tool each layer, no learning.
2. **greedy-cheapest** — argmin(cost + latency-scaled) per layer, no learning.
3. **greedy-advertised** — argmax η per layer, no learning. This is the
   "trusts ads forever" strawman the ACO router must beat.
4. **oracle** — brute-force all 9 paths per query *type* using TRUE profiles
   (expected reward), precomputable per type. Upper bound, not a real method.

All produce `(path, quality, cost, latency)` per query.

### experiment.py / metrics.py / viz.py (M6.5–M6.7)
- Runners: 100 queries × 5 seeds × all methods, identical query stream and
  sabotage schedule across methods.
- Metrics: cumulative reward, final mean quality, mean cost, rolling utility
  learning curve, per-tool traffic share time series.
- Viz: convergence plot, sabotage money plot (traffic shares, vline at #50,
  PNG + GIF), τ heatmaps at queries 25/50/75/100.

## Design risks / open decisions (flagged for human)

These are the things I'd change or need a ruling on before coding:

1. **R1 — Reward can be negative, and the update assumes positive deposits.
   — RESOLVED (human decision, kickoff): clip the deposit at ≥ 0**
   (`τ += Q · max(0, R)`), keeping raw (possibly negative) R for
   reporting/metrics so the reward definition is untouched. Matches classic
   ACO, which deposits only positive quantities.

2. **R2 — Latency penalty dominates the cost penalty by ~10×.**
   /1e3 for ms vs /1e4 for tokens means latency matters ~10× more per unit.
   Consequence: the router may learn "always pick fast tools" more than
   "pick good tools", and the sabotage recovery (latency×3 on web_search)
   could be driven by latency alone, weakening the "quality learning" story.
   Proposal: keep λ=1 as specified (it's the charter) but log in
   diagnosis-log.md whether recovery is latency-driven or quality-driven.
   If it's latency-only, M6.6's claim needs a second sabotage variant
   (quality drop with NO latency change) as a control. I'll flag this when
   we get there.

3. **R3 — Shared τ vs per-type τ.**
   The charter says τ is a 2×3 matrix per layer (shared across query types),
   but M6.7 wants heatmaps "split by query type" showing math routing
   differently from factual. With shared τ, type separation comes only
   through η (which differs per type). That works — but the *heatmap* then
   shows routing *probabilities* (τ·η combined), not raw τ. Proposal: single
   shared τ (more faithful ACO, richer learning dynamics), and M6.7 plots
   the **effective transition probabilities per type** + per-type traffic
   shares. Per-type τ (a 2×3×4 tensor) would learn faster but is less
   "ant-colony" and closer to 4 independent bandits. Decision needed:
   **shared τ (recommended)** or per-type τ.

4. **R4 — Evaporation cadence vs recovery speed.**
   ρ=0.05 per batch of 10 queries ⇒ web_search's pheromone halves roughly
   every ~135 queries if it gets zero deposits. The M6.6 DoD requires traffic
   share <20% within 30 queries of the sabotage. That recovery must come
   almost entirely from *relative* dynamics (rivals getting all the deposits
   while web_search's share of deposits collapses) rather than absolute
   evaporation. Probably fine (the transition normalizes), but if recovery
   is too slow, ρ or ε is the knob — and per working rule 4, a too-slow
   recovery gets *logged, not silently tuned away* in the first M6.6 run.

5. **R5 — "Beats greedy-advertised" may be nearly guaranteed by design.**
   Greedy-advertised always picks the loudest ad, and we deliberately
   mislead on 1–2 pairs, so the ACO router winning ≥4/5 seeds is a low bar.
   Fine as a DoD, but the *interesting* comparison is vs oracle (within 10%)
   — and the misleading ads must be strong enough that greedy-advertised
   visibly loses on the misled types, or the demo teaches nothing. I'll
   tune ad-noise so greedy-advertised's loss is visible but not cartoonish.

6. **R6 — Deposit per query vs per batch. — RESOLVED (human decision, kickoff):
   deposit immediately after each query; evaporation stays at the batch
   boundary.** Rationale: recovery speed is the flagship metric (a
   batch-end deposit would burn ~9 of the 30-query recovery window on stale
   pheromone), per-query deposit preserves within-batch ordering
   information, and Searchy's sequential query stream has no parallel
   colony, so immediate deposit is the honest translation of AS's
   per-iteration deposit. This divergence from the original Ant System is
   itself material for the "vs the original" comparison (R1.2).

## DoD for this milestone

Human approves this doc (or requests changes). Then: commit, tag `m6.1`.