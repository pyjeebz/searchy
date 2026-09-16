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