# Diagnosis Log — observed-weird-behavior record

Implements working rule 4. Every strange observation in experiments gets an
entry here: what we saw, how it was measured, what we suspected, what we did
(and what we deliberately did NOT patch). These entries drive the human's
reading (R-items) and the blog. **Do not silently patch entries away.**

Format:

```
## D<n>. <short title> (<milestone>, <date>)
- Observed: <what happened, with numbers>
- Reproduced: <seeds/conditions>
- Suspicion: <hypothesis>
- Action: <what we did about it — including "nothing, left as material">
- Reading trigger: <R-item it feeds, if any>
```

---

## D1. Reward scale defect: every path punished below zero (M6.3 build, 2026-09-15)
- Observed: while implementing the router's reward, hand-checking the
  charter formula against the committed M6.2 magnitudes showed the penalty
  term exceeds the *maximum achievable quality product* for every path:
  e.g. web_search+small_llm → 4500/1e4 + 2000/1e3 = 2.45 penalty vs
  quality product ≤ 0.57. Best expected reward over all 9 paths × 4 types
  is negative (≈ −0.23). With the R1 ruling (deposit clipped at ≥0), every
  deposit would be zero and τ could never learn — M6.3 DoD unreachable.
- Reproduced: arithmetic on the committed constants (tools.py at tag
  m6.2); not seed-dependent.
- Suspicion: the charter's /1e3 latency divisor implies latencies in the
  tens of ms; the design doc's rough magnitude targets (hundreds of ms)
  were carried into M6.2 without checking them against the reward scale.
- Action: rescaled costs/latencies ~5–10× down (web_search 500 tok/60 ms,
  small_llm 1000/90, …, calculator 60/5), keeping the charter formula
  (λ=1, /1e4, /1e3) untouched. Penalties now land at 0.04–0.30 against
  quality products of 0.02–0.71: quality dominates, cost stays a real
  second-order trade-off (reward-best paths: factual web_search+small_llm
  +0.27, math knowledge_base+calculator +0.30, summarization
  vector_db+small_llm +0.49, code vector_db+regex +0.41). Regression test
  added (best expected reward per type > 0.2). Design doc amended. NOT
  touched: λ and the scale divisors — those are charter-specified.
- Reading trigger: none (build defect, not emergent behavior); interacts
  with R5 (misleading-ad strength, see D2).

## D2. Misleading ads pointed at the reward-optimal path (M6.3 build, 2026-09-15)
- Observed: the originally approved misleading pairs did not hurt
  greedy-advertised once *rewards* (not raw quality) drive choices.
  knowledge_base's math oversell (ad 0.90) accidentally advertises the
  optimal retrieve choice — kb+calculator is genuinely the reward-best
  math path because kb is cheap. vector_db's factual oversell (ad 0.85)
  rarely flips greedy's choice because web_search's honest 0.95 ad
  dominates anyway. The "colony must learn to distrust ads" story had
  no teeth.
- Reproduced: expected-reward table over all 9 paths per type with the
  committed profiles and (pre-D1) costs.
- Suspicion: the pairs were chosen in M6.1 against the *quality*
  landscape before accounting for the reward formula's cost term.
- Action: re-targeted to knowledge_base→summarization (ad 0.90, true
  0.50 — oversell) and calculator→math (ad 0.30, true 0.98 — undersell).
  Greedy-advertised now visibly loses on the misled types: math greedy
  expected reward ≈ −0.03 vs best +0.30; summarization greedy +0.25 vs
  best +0.49. Still exactly 2 misleading pairs (R5: visible, not
  cartoonish). Honest side effect: the ad-noise generator skips
  overridden pairs, so changing which pairs are overridden shifts the
  noise draws of the other pairs — all ads remain seeded-deterministic
  and within 4σ of true (tests enforce both).
- Reading trigger: R5 (ad-strength tuning watch-item).

## D3. Premature convergence: colony freezes near the advertised frontier (M6.3 build, 2026-09-15)
- Observed: probe of the finished router (5 router seeds, one fixed
  100-query stream, inline greedy-advertised comparison using expected
  qualities) shows: (a) process layer locks onto small_llm fast and hard
  (τ ≈ 13 vs ≤ 2.5 for calculator/regex after 100 queries — small_llm is
  genuinely best for 3 of 4 types); (b) retrieve layer stays mixed across
  seeds (argmax τ differs by seed: web_search 3/5, knowledge_base 1/5,
  vector_db 1/5); (c) mean realized reward is flat over the stream
  (first50 ≈ last50 in every seed) — the colony reaches a good-enough
  equilibrium within ~the first ad-following phase and then barely moves;
  (d) overall mean reward +0.166…+0.187 vs greedy-advertised +0.169
  (expected): a near-tie, with the router ahead on summarization/code,
  behind on factual (ε-exploration tax), and stuck with everyone else on
  math; (e) oracle mean is +0.37 — nobody gets near it.
- Reproduced: router seeds 0–4 on query-stream seed 100; numbers above.
- Suspicion: positive-feedback lock-in. calculator's undersold math ad
  (0.30) starts it at P ≈ 16% for math queries; every small_llm win from
  ANY type deposits through the shared τ (R3), so small_llm's τ grows
  ~3× faster than calculator's and calculator's math probability decays
  toward ~2% by query 100 — the undersell is never overcome within 100
  queries. Evaporation (ρ=0.05/10 queries) is far too weak to unseat an
  incumbent; ε=0.1 exploration only slows the lock-in.
- Action: nothing yet — deliberately not tuned (working rule 4; also the
  charter's R4 ruling: log, don't silently retune). This is honest,
  expected ACO behavior (premature convergence is *the* classic ACO
  failure mode) and prime material: it is the demo evidence for why the
  literature invented MMAS pheromone bounds (R2.1), ACS q0-exploitation
  (R2.2), and restarts (M7.2) — the Stage-4 backport now has a concrete
  before-picture to fix. Risk flagged: M6.5's "beat greedy-advertised on
  ≥4/5 seeds" will be marginal at these parameters (currently 4/5 by
  ≤0.02), and M6.6's 30-query sabotage recovery may be slow for the same
  lock-in reasons (R4). If M6.5/M6.6 DoDs fail, the honest options are
  tuning ε/ρ/β, a longer stream, or reporting the negative result.
- Reading trigger: R1.2 (our loop vs the original), R2.1 (MMAS bounds),
  R2.2 (ACS exploitation), R4, R5.

## D4. M6.5 verdict: a split negative result — parity with the strawman, half of oracle (M6.5 run, 2026-09-16)
- Observed: the M6.5 DoD fails, via its sanctioned negative-result path.
  Clause (a) — beat greedy-advertised on cumulative reward on ≥4/5 seeds —
  technically MET at exactly 4/5, but the margins are +0.05, +2.37, −0.24,
  +0.76, +1.14 across seeds 0–4: seed 0 wins by a rounding error, seed 1's
  outlier carries the clause, seed 2 loses (cumulative means: router
  17.70 ± 0.71 vs greedy-advertised 16.88 ± 0.35). Clause (b) — within 10%
  of the oracle's mean utility — NOT MET by a wide margin: router +0.177
  vs oracle +0.365, ratio 0.486. More honest than either clause: the
  router's *after-learning* quality (final 25 queries) is 0.411, BELOW
  greedy-advertised's 0.429 — its cumulative edge is mostly the cost term
  (mean 1125 vs 1318 tokens, 110.5 vs 128.8 ms), i.e. it discovered
  cheaper tools, not better paths. Per type it wins slightly on
  summarization (+0.273 vs +0.246) and code (+0.238 vs +0.218), loses on
  factual (+0.227 vs +0.266, the ε-exploration tax D3(d) predicted), and
  stays negative on math (−0.030 vs oracle +0.295 — the calculator
  undersell is still never overcome).
- Reproduced: 5 seeds × 100 queries on one shared stream (query_seed 100),
  M6.3 router parameters verbatim (α=1, β=2, ε=0.1, ρ=0.05, Q=1, τ0=1,
  batch 10). Committed under experiments/results/m6.5-comparison/
  (records.csv, summary.csv, summary.json); figure at
  experiments/results/figures/m6.5-convergence.png — the learning curve is
  *flat* for the router from query ~5 onward: it starts at its plateau,
  hugging greedy-advertised, never approaching oracle (D3(c) again).
- Suspicion: the D3 lock-in mechanism, now measured end-to-end. Shared τ +
  immediate deposit + weak evaporation converge to the advertised frontier;
  the oracle's entire edge sits in the two paths the ads steer away from
  (math knowledge_base+calculator, summarization vector_db+small_llm), and
  the colony cannot reach them in 100 queries. Clause (b) was structurally
  unreachable at these parameters; clause (a) passes only on a cost
  artifact plus one lucky seed.
- Action: reported as a measured negative result; NOTHING tuned (working
  rule 4). Options on the table for the human, none taken: raise ε, raise
  ρ, lower β, or lengthen the stream — each changes the demo's story and
  is the human's call. The honest one-line summary for the blog is
  "indistinguishable from the strawman it was meant to beat, at half the
  oracle" — which is precisely the Stage-4 before-picture: MMAS pheromone
  bounds + restarts (M6-RT backport) exist to fix exactly this.
- Reading trigger: R2.1 (MMAS bounds), R2.2 (ACS exploitation), R1.2;
  direct before-picture for the M6-RT backport.

## D5. M6.6 verdict: the DoD fails — and the first run overstated recovery via a window-start artifact (M6.6 run, 2026-09-16)
- Observed (artifact first, since it changed a reported number): the
  first run of the sabotage demo printed the recovery clause as MET 4/5.
  Inspection of the per-seed pass queries showed all four "passes" at
  queries #50–#51 — one and two queries after the event — where the
  trailing 10-query rolling window is 90% and 80% pre-event queries. The
  rolling mean there still reports mostly pre-sabotage rewards; crediting
  it as "recovery" is a measurement artifact, not adaptation. Caught
  during result review, before any conclusion was drawn from it — this
  is exactly what working rule 4 exists for.
- Fix (measurement, not model): recovery is now credited only from
  query #59 onward (= event #50 + rolling window 10 − 1), the first
  query whose trailing 10-window lies entirely in the post-event half.
  Window-start passes are still computed and reported separately as
  `recovery_clause.n_pass_incl_window_start` so the artifact stays
  visible in every future summary instead of vanishing. Validation also
  rejects a rolling_window larger than the DoD adaptation window (there
  would be no fully-post-event index at all). Regression test:
  tests/test_sabotage.py::test_window_start_pass_excluded_before_damage_arrives.
- Corrected honest verdict (5 seeds, shared stream, M6.3 parameters
  verbatim, event #50: web_search true quality → 0.05, latency ×3, ads
  unchanged): share clause 3/5 NOT MET (required 4; seeds 0 and 3 bottom
  out at exactly 0.20 and the clause is strict); recovery clause 1/5 NOT
  MET (required 4; only seed 1, at #69); DoD NOT MET on the conjunction.
  With the artifact left in, recovery would have read 4/5 MET — the fix
  makes the result strictly worse, and that is the honest direction.
  Per-seed end-of-window rolling rewards +0.059, −0.049, +0.015, +0.039,
  +0.110 against recovery targets 0.163–0.225.
- Mechanism (why recovery genuinely fails): web_search's Layer-1 share
  plateaus at ~0.10–0.20 instead of collapsing toward 0, and utility
  stays far below the pre-event level (steady-state rolling ≈ +0.08 vs
  pre-event ≈ +0.17, target 0.9×). Three compounding causes, all visible
  in the code: (a) the R1 deposit clip — bad picks deposit 0 but are
  never punished, so τ_web_search can only decay via evaporation (×0.95
  per 10-query batch → ≈0.77 over the 50-query post-event half), (b) the
  lying ads keep β=2 amplifying web_search's advertised 0.95 every step,
  and (c) ε=0.1 exploration keeps re-feeding it ≈3.3% of Layer-1
  traffic. The colony cannot actively unlearn a once-popular tool —
  D3/D4's lock-in mechanism under a harder test.
- What the demo does show honestly: the router is the only learner in
  the pool. Post-event mean reward +0.035 vs greedy-advertised −0.129;
  per-seed pre-event web_search share 0.58/0.55/0.24/0.36/0.24 falls to
  a window minimum of 0.20/0.10/0.10/0.20/0.10 — real traffic moved off
  the sabotaged tool in every seed — but real-but-insufficient
  adaptation is the finding, not a pass. The oracle re-picks instantly
  (+0.365 post-event); greedy-advertised walks into the sabotage on
  every factual query. Money plot produced as required (PNG + GIF at
  experiments/results/figures/), showing share collapse + reward dip
  despite the failed clauses.
- Action: reported as a measured negative result; NOTHING tuned (working
  rule 4). Both ROADMAP clauses fail; the honest-negative path is taken.
  Reinforces D3/D4 and sharpens the Stage-4 M6-RT backport: with MMAS
  pheromone bounds, lying ads could not prop up a collapsed tool; with
  restarts the colony could escape the plateau. No changes to M6.7
  (heatmaps are purely descriptive).
- Reading trigger: R2.1 (MMAS bounds), R2.2 (ACS exploitation), R1.2, R4;
  direct before-picture for the M6-RT backport.
## D6. AS transition rule shipped without its exponents (M3.1 build, 2026-10-02)
- Observed: first AS runs on eil51 (51 ants × 200 iters, 10 seeds) gave a
  median gap of 13.50% and IDENTICAL results for beta=2 and beta=5 — the
  heuristic weight had no effect, which is impossible if the transition
  rule is implemented correctly.
- Reproduced: 10-seed medians matched to the second decimal across both
  beta settings; inspection of _construct_tour found
  ``scores = tau[current] * eta[current]`` — the α and β exponents of the
  documented rule τ^α·η^β were never applied (α=1 made the pheromone side
  silently correct; β was a no-op).
- Suspicion: the exponent application was dropped while translating the
  docstring's formula into code; because α=1 is the default, only the β
  ablation exposed it. A useful smoke: parameter ablations that change
  nothing are implementation bugs until proven otherwise.
- Action: exponents applied (scores = tau**alpha * eta**beta), alpha/beta
  threaded into _construct_tour; regression test added
  (tests/test_tsp_aco.py::test_alpha_beta_actually_applied — beta=0 must
  behave differently from beta=6). After the fix: eil51 median gap 6.22%
  (mean 5.47%, min 2.82%, max 7.04%) — M3.1 DoD (<8%) met. The pre-fix
  numbers are kept here as the honest build record.
- Reading trigger: none (build defect, caught by ablation); the β=2 vs β=5
  equivalence on the broken build is a cautionary note for Post 4's
  parameter-discipline story.

## D7. Plain AS (rho=0.5) outperforms our first-cut MMAS on eil51 (M3.5 build, 2026-10-02)
- Observed: MMAS (iteration-best deposits, Stützle-Hoos bounds, ρ=0.02,
  51 ants × 500 iters) best-tour gaps on eil51 seeds 0–4: 7.51/8.45/9.39/
  5.63/6.57% (mean 7.51%). Plain AS from M3.1 at only 200 iterations and
  ρ=0.5 reached e.g. 2.82–7.04% (seed 0: 438 = 2.82%; the strong-evaporation
  regime keeps AS's unbounded τ from locking in). The literature's ordering
  (MMAS > AS) is reversed in our first cut.
- Reproduced: 5 MMAS seeds vs the committed M3.1 AS numbers; same
  construction rule, same instance, same budget convention (m=n).
- Suspicion (three candidates, all standard MMAS subtleties): (a) τ0 mode —
  we initialize τ = tau_max, which with ρ=0.02 and iteration-best deposits
  gives very flat early pheromone and slow take-off; (b) the tau_min factor
  0.001·n·tau_max may be too permissive, letting near-zero edges keep
  non-trivial probability and slowing convergence; (c) 500 iterations of
  MMAS at ρ=0.02 may simply be a different budget than AS's fast ρ=0.5
  cycle — MMAS's advantage in the literature is at larger budgets and with
  2-opt local search (M3.6), which we have not added yet.
- Action: logged, not tuned — M3.5's DoD is anti-stagnation (MET: diversity
  min 51/51 across 500 iters, longest diversity==1 streak 0, restarts
  firing 6–8× per run), not beat-AS. The AS-vs-MMAS comparison belongs to
  M4-L's equal-budget table (with 2-opt applied to both), where the
  protocol equalizes iterations × ants and reports Wilcoxon p-values.
  If MMAS still loses there, that is a finding for Post 4, not a tuning
  session (working rule 4). Human's R2.1 reading (MMAS) may also
  diagnose this directly.
- Reading trigger: R2.1 (MMAS parameter subtleties — τ0 mode, bound ratios,
  budget interaction); feeds Post 3 ("the literature knew") and Post 4.

## D8. M4-L table: MMAS without local search loses to plain AS on all 3 instances (M4-L, 2026-10-02)
- Observed: equal-budget table (10 seeds, 100 iters, m=n), no-LS rows:
  MMAS median gaps 11.50/7.64/18.28% vs AS 6.81/2.78/10.17% (eil51/
  berlin52/eil101). Wilcoxon: MMAS worse than AS on every instance
  (p ≈ 1.5e-4 each). With 2-opt applied to every ant tour, the two
  variants converge (eil51 p=0.66, berlin52 p=1.0 — both hit the optimum
  on all seeds) except eil101 where AS+2opt stays ahead (p=0.015).
- Reproduced: 12-job parallel protocol, byte-identical one-command repro
  verified; see experiments/results/m4l-tsp/.
- Suspicion: resolves D7 — the MMAS literature advantage presumes local
  search (the paper's results pair MMAS with 2-opt); our τ0=tau_max flat
  start + slow ρ=0.02 is dominated by AS's fast ρ=0.5 cycle at small
  budgets. The bounds mechanism itself (anti-stagnation) is orthogonal —
  M3.5's DoD measured it working (diversity 51/51, restarts firing).
- Action: reported as the table's headline finding, nothing tuned: "the
  variant matters less than whether you refine at all" — 2-opt's median
  improvement is 6.8–16.6 points of gap, vs ≤1.6 between variants+LS.
  Also the honest protocol note: reduced grid (10 seeds × 100 iters) for
  wall-clock; stated in every caption. Feeds Post 4 (stats discipline)
  and the demo video's Act-2 narration.
- Reading trigger: R2.1 (MMAS), R2.3 (variants table — this IS the
  "fixes to bugs we saw" centerpiece row).

## D9. Overlay reward scale: raw credits price quality out of learning (FO.2 build, 2026-10-02)
- Observed: first overlay run showed /search traffic share climbing from
  0.37 to 0.90 — looked like learning — but tau inspection showed the
  matrix IDENTICAL (1.0, 1.0) for the entire stream: deposits never
  flowed. The share drift was the query MIX (docs queries advertise
  /map; news/product/factual advertise /search), not pheromone.
- Reproduced: per-query reward computation showed EVERY option nets a
  negative reward at the raw-credit scale (base 1-credit price exceeds
  the 1.0 max quality; scrape latencies add 1-12 more). With the R1
  deposit clip (max(0, R)), every deposit is 0 → tau frozen forever.
- Suspicion: the same defect class as Searchy's D1 — the cost scale was
  set without checking it against the quality scale. Caught here by
  auditing tau directly (the same probe that caught the M3.1 exponent
  bug, D6: a mechanism that isn't moving is a bug until proven
  otherwise).
- Action (a priori, stated in every caption, mirroring the D1 ruling):
  reward cost term scaled by COST_SCALE=50 — a typical scrape's penalty
  is ~0.04 vs quality 1.0, a recorded ~90s timeout ~0.26. Deposits now
  flow (markdown tau 1.0 → 31.2 vs json → 8.0 over the stream). Product
  metric for the FIGURE stays raw (API credits + latency-equivalents at
  7.7s/credit) — with per-call pricing every policy spends the same 50
  API credits, so the honest savings live in latency-equivalents and
  quality, and the caption says exactly that.
- Reading trigger: none (build defect); cautionary-tale companion to
  D1/D6 for the blog's "parameter discipline" thread.

## D10. Overlay honest result: exploration can't pay for itself in 25 queries when the default is right (FO.2, 2026-10-02)
- Observed: measured effective cost (API credits + latency-equivalents):
  always-search-markdown 57.5 < router 87.5 < random 101.0 (p=0.0038,
  30 seeds each) < always-map-json 148.9. The router beats random and
  the wrong default decisively (61.4 effective credits saved, 41%), but
  LOSES to the obvious right default by ~30.
- Reproduced: 30 seeded router runs over the committed fixtures; the
  static policies are deterministic functions of the same fixtures.
- Suspicion: none — mechanism understood. The 25-query stream is too
  short for ε=0.1 exploration to amortize: the uniform start + 10%
  lifelong exploration tax costs ~0.7 effective credits/query, and the
  right default pays zero learning cost. With a longer stream or a
  WRONG default config (the realistic enterprise case: defaults are
  static, domains shift), the router's learning pays.
- Action: reported as the honest headline — no tuning, no stream
  extension to manufacture a win (charter rule: claims are measured).
  The demo caption leads with the defensible claim: "beats random
  (p=0.004) and saves 41% vs the wrong static default; loses to the
  right default on a 25-query stream — the crossover is future work."
  Post 6 (overlay section) gets the full treatment.
- Reading trigger: R1.1 (exploration/exploitation); feeds the overlay
  doc's "what I'd do differently" row (decay ε over the stream).

## D11. M6-RT backport: bounds help the comparison and recovery, not the share clause (M6-RT, 2026-10-03)
- Observed: BoundedPheromoneRouter (MMAS bounds Q/best_reward with ratio 8,
  restart after 20 stagnant queries; everything else inherited verbatim)
  on the identical M6.5/M6.6 protocol: comparison cumulative reward
  17.70 → 18.58 (+5.0%, same 5 seeds/stream); sabotage share clause
  3/5 → 2/5 (WORSE), recovery clause 1/5 → 2/5 (better). DoD still not
  met (needs 4/5 on both).
- Reproduced: per-seed table shows the share clause misses at exactly
  0.20 on three seeds (strict <) — the bounded floor tau_min keeps
  web_search reachable, and restarts (firing 2-3x per run, often at/after
  the #50 event) deliberately re-explore ALL tools including the
  sabotaged one.
- Suspicion: mechanism understood, not a bug — tau_min bounds the
  probability ratio at 8x, so a sabotaged tool can never be fully
  abandoned (by design: it might recover, and the epsilon floor kept
  ~3% share anyway in the plain router). The recovery improvement is
  where the mechanism pays: bounded tau lets evaporation actually drag
  the lying-ad score down, so realized rewards recover faster (seeds
  0/1 now pass vs 1 before).
- Action: reported honestly as a MIXED result; nothing tuned (rule 4).
  The demo story is now sharper: bounds trade share-collapse for
  recovery speed — a Pareto move, not a strict win. Post 5 gets the
  honest "I backported the literature's fix and it half-worked" arc.
- Reading trigger: R2.1 (MMAS bound ratios), R2.3 (variants table row);
  feeds M7.4's combined claim.

## D12. M7 improvements grid: one significant win, one significant loss, mostly wash (M7.1-M7.4, 2026-10-03)
- Observed (10 seeds x 100 iters, identical protocol to the M4-L
  baselines, Wilcoxon per pair): nn_init significantly improves plain
  AS on eil51 (median 5.52% vs 6.81% gap, p=0.040) — the ONE clean
  positive. The combined variant is significantly WORSE than AS+2opt on
  eil51 (median 0.23% vs 0.00%, p=0.044) — the one clean negative: at
  eil51's tiny post-2opt margins, nn_init's greedy prior actively hurts
  the refined search. Restart: p>=0.26 everywhere (the 100-iter
  horizon never stagnates long enough to matter). Candidates k=20:
  p>=0.52 on quality; runtime +12% (eil51) to +44% (eil101) faster
  construction — the honest M7.3 claim is RUNTIME, not quality.
- Reproduced: 4 parallel variant runs over the committed baselines;
  every number in experiments/results/m7-*/summary.json.
- Suspicion: all three mechanisms are known to matter most at (a)
  larger instances, (b) longer budgets, (c) without 2-opt hiding their
  effect. Our lean 100-iter/3-instance protocol (chosen for wall-clock)
  is exactly the regime where they wash. This is the D8 lesson again:
  2-opt dominates everything; the improvement mechanisms fight over
  scraps.
- Action: M7.4's GATE claim is taken honestly: "NN-init improved plain
  AS by 1.3pp median gap on eil51 (p=0.04, n=10); candidate lists cut
  construction time up to 44% at equal quality (p>0.5); the combined
  variant bought nothing (one significant negative at eil51+2opt).
  Improvements wash under 2-opt at this scale." Nothing tuned. Post 5
  title earns its question mark.
- Reading trigger: R2.3 (variants table: which fixes matter when);
  the honest-negatives log (M7.5) IS this entry.
