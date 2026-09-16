# PROGRESS — ACO Demo-First

Legend: `[me]` = human-owned (reading / blog writing), `[agent]` = agent-owned
(code / experiments / scaffolding). Update after every milestone; one commit +
tag per milestone.

## Kickoff / scaffold
- [x] [agent] Repo scaffold + CLAUDE.md + ROADMAP.md + PROGRESS.md (tag: kickoff)

## Stage 1 — Primer + Build (Weeks 1–3)
- [x] [agent] R0.1 scaffold — docs/primer.md written (human gate: rewrite
      transition rule + update equation from memory → **pending**)
- [x] [agent] M6.1 design doc — docs/design-searchy.md written
      (**APPROVED 2026-09-15** — risks R1/R3/R6 resolved, tag m6.1)
- [x] [me]   R0.1 gate — read primer, pass from-memory test
      (**PASSED 2026-09-15** — human notes)
- [x] [agent] M6.2 queries.py + tools.py (**DONE 2026-09-15**, tag m6.2 —
      100 seed-deterministic queries, 6 tools with misleading ads,
      18 tests passing)
- [x] [agent] M6.3 router.py + reward.py (ACO core) (**DONE 2026-09-15**, tag
      m6.3 — transition rule τ^α·η^β with ε-exploration, immediate clipped
      deposit, batch evaporation; 34 tests passing. Build findings logged
      as D1–D3 in docs/diagnosis-log.md, incl. two corrections to M6.2
      constants — human review welcome, veto = git revert)
- [x] [agent] M6.4 baselines.py (**DONE 2026-09-15**, tag m6.4 — random,
      greedy-cheapest, greedy-advertised, oracle; 44 tests passing. Oracle
      beats greedy-advertised by +0.36/+0.24/+0.20 expected reward on the
      three misled types, equal on factual — the D2 ads have teeth)
- [x] [agent] M6.5 comparison experiment (100 queries × 5 seeds) (**DONE
      2026-09-16**, tag m6.5 — 55 tests passing. SPLIT NEGATIVE RESULT
      (D4): clause (a) met at the bare minimum — router beats
      greedy-advertised on 4/5 seeds, margins +0.05/+2.37/−0.24/+0.76/
      +1.14, and the edge is cost-side (final quality 0.411 is BELOW the
      strawman's 0.429); clause (b) failed hard — router at 48.6% of
      oracle utility. Learning curve flat from query ~5. Nothing tuned)
- [x] [agent] M6.6 sabotage demo (money plot + GIF) (**DONE 2026-09-16**,
      tag m6.6 — 75 tests passing. Measured NEGATIVE RESULT (D5): share
      clause 3/5, recovery 1/5 — DoD NOT MET, nothing tuned. First run's
      "recovery MET 4/5" was a window-start artifact, caught in review and
      fixed; the corrected result is strictly worse and honestly reported.
      Router does adapt (+0.035 post-event vs greedy −0.129) but plateaus
      at 0.10–0.20 web_search share, short of 90% recovery. See the
      decision log entry below for the full verdict)
- [ ] [agent] M6.7 pheromone heatmaps
- [ ] GATE 1 — 2-min narratable demo + all artifacts

## Stage 2 — Diagnosis-driven reading (Weeks 3–5) — [me]
- [ ] [me] R1.1 trigger seen: router stagnation/recovery → read Dorigo & Stützle ch.1–2 → unlock: Post 2 mechanics
- [ ] [me] R1.2 trigger seen: comparing our loop to the original → read Dorigo/Maniezzo/Colorni 1996 → unlock: Post 2 "vs the original"
- [ ] [me] R2.1 trigger seen: τ collapse or over-dominance → read Stützle & Hoos 2000 (MMAS) → unlock: Post 3 pheromone bounds
- [ ] [me] R2.2 trigger seen: exploitation questions → read Dorigo & Gambardella 1997 (ACS) → unlock: Post 3 q0/exploitation
- [ ] [me] R2.3 variants comparison table (AS/ACS/MMAS × 6 attributes) as "fixes to bugs we saw" → unlock: Post 3 centerpiece
- [ ] [me] R3.1 skim AMRO-S + ACO-ToT → unlock: Post 2 sidebar (honest similarities AND differences)
- [ ] [me] R3.2 read DyNACO anti-stagnation idea → unlock: Post 5 improvement idea

## Stage 3 — Canonical test: TSP (Weeks 5–7)
- [ ] [agent] M0.2 TSPLIB loader (EUC_2D) — sanity: eil51 NN ≈ 426±15%, berlin52 opt 7542, eil101 opt 629
- [ ] [agent] M0.3 nearest-neighbor baseline
- [ ] [agent] M3.1 AS from scratch on eil51 — median gap <8% over 10 seeds
- [ ] [agent] M3.2 convergence GIF + pheromone heatmap
- [ ] [agent] M3.3 logging harness (best/mean/diversity → CSV → plots)
- [ ] [agent] M3.4 ACS — beats our AS median on eil51
- [ ] [agent] M3.5 MMAS + restarts — diversity ≠ 0 for 50 consecutive iterations across 500
- [ ] [agent] M3.6 2-opt refinement + runtime-share measurement
- [ ] [agent] M4.1–M4.3 experiment runner + metrics + Wilcoxon rank-sum p-values
- [ ] [agent] M4.4 baseline study table (5 instances × 30 seeds, equal budget) — GATE: one-command reproduction

## Stage 4 — Improvements, proven (Weeks 7–9)
- [ ] [agent] M7.1 NN-tour pheromone init vs uniform τ0 (5 × 30)
- [ ] [agent] M7.2 stagnation restart OR adaptive ρ (same protocol)
- [ ] [agent] M7.3 candidate lists k=20 on largest instance
- [ ] [agent] M7.4 combined improved-AS vs AS and MMAS+2-opt, p-values — GATE: "X improved Y by Z% (p<0.05, n=30)"
- [ ] [agent] M7.5 honest negative-results log
- [ ] [agent] M6-RT backport MMAS bounds + restart to Searchy; re-run M6.5/M6.6; before/after plots

## Stage 5 — Blog arc — [me] writes
- [ ] [agent] Scaffold blog/posts/ stubs (done at kickoff)
- [ ] [me] Post 1 (~W3): "I Built a Search Agent That Routes Like an Ant Colony"
- [ ] [me] Post 2 (~W4–5): "How ACO Actually Works — Explained by a System I Built First"
- [ ] [me] Post 3 (~W6): "Everything I Got Wrong, the Literature Knew by 2000"
- [ ] [me] Post 4 (~W8): "Does ACO Hold Up on the Traveling Salesman Problem? A Controlled Study"
- [ ] [me] Post 5 (~W10): "Can You Improve Ant Colony Optimization? I Ran 30 Seeds (Twice)"

## Decision log
- 2026-09-15: Project root is `/home/pyjeebz/searchy` (scaffolded in the
  existing working directory rather than creating an `aco-project/` subfolder —
  same layout, one less nesting level).
- 2026-09-15: Deposit cadence (design risk R6): deposit immediately after
  each query; evaporation per batch of 10. Human decision at kickoff review.
- 2026-09-15: Negative rewards (design risk R1): clip the pheromone deposit
  at ≥0 (`τ += Q·max(0, R)`); raw R kept for all metrics. Human decision at
  kickoff review.
- 2026-09-15: Pheromone structure (design risk R3): single shared 2×3 τ
  matrix across query types; type separation flows through η. M6.7 heatmaps
  show effective routing probabilities (τ·η) per type. Human decision at
  kickoff review.
- 2026-09-15: Design doc approved; primer gate passed. M6.1 closed (tag m6.1).
- 2026-09-15: Git workflow: file-by-file commits with conventional commit
  messages; no milestone IDs in messages. Charter tags (kickoff, m6.1, ...)
  kept, applied after the milestone's commits.
- 2026-09-15: During the router build two M6.2 constants were corrected,
  logged as D1/D2 in docs/diagnosis-log.md and amended into the design doc
  (human may veto; revert is clean): (D1) tool costs/latencies rescaled
  ~5–10× down — the original magnitudes made every expected reward negative
  and, with the deposit clip, all deposits zero; (D2) misleading ads
  re-targeted to knowledge_base→summarization (oversell) and
  calculator→math (undersell) — the original pairs advertised the
  reward-optimal path. Charter reward formula (λ=1, /1e4, /1e3) untouched.
- 2026-09-15: D3 (premature convergence probe: colony freezes near
  greedy-advertised, calculator never discovered within 100 queries) was
  logged, not tuned, per working rule 4. It is expected ACO behavior and
  the before-picture for the Stage-4 MMAS/restart backport. M6.5's
  beat-greedy DoD will be marginal at current parameters; M6.6 recovery
  speed is at risk (R4). No parameter changes without human go-ahead.
- 2026-09-15: Baseline design decisions (M6.4): (a) greedy-cheapest's
  "latency-scaled" cost = the charter's own penalty scale
  (tokens/1e4 + ms/1e3), argmin per layer — type-blind by construction;
  (b) every baseline *executes* through call_tool on the passed
  generator, so per-query realized rewards are directly comparable to
  the router's (each method is a self-contained process; the query
  stream, pool, reward function, and call-noise model are shared, the
  noise draws are not). The oracle is the upper bound *in expectation*
  — its selection uses true profiles, its realized rewards still face
  call noise. Paired-draw variance reduction is deliberately NOT built
  in; if M6.5's tight comparisons need it, that is an experiment-design
  decision to make then.
- 2026-09-16: M6.5 closed as a measured negative result (D4 in
  docs/diagnosis-log.md): the router ties greedy-advertised (4/5 seeds,
  thin margins, edge is cost not quality) and reaches only 48.6% of
  oracle utility. The ROADMAP's alternative branch — "measured negative
  result + diagnosis-log entry" — was taken; ε/ρ/β and stream length all
  untouched. Options raised for the human: tune ε/ρ/β, lengthen the
  stream, or proceed as-is to M6.6/M6.7 and let Stage 4 (MMAS bounds +
  restarts, M6-RT) fix it — the demo-first bet is that the failure IS
  the demo material.
- 2026-09-16: M6.6 closed as a measured negative result, plus a caught
  measurement artifact (D5 in docs/diagnosis-log.md). The sabotage demo
  ran as specified (event #50, 5 seeds, shared stream, M6.3 parameters
  verbatim); its first run's recovery clause read MET 4/5 but every pass
  sat at #50–#51, where the rolling window was still ≥80% pre-event
  queries — a window-start artifact, not adaptation. After restricting
  recovery to fully-post-event windows (window-start passes kept
  visible as n_pass_incl_window_start, regression test added), the
  verdict is: share clause 3/5 (needs 4; strict 0.20 misses on seeds
  0/3), recovery clause 1/5 (only seed 1, at #69) — DoD NOT MET,
  reported honestly, nothing tuned. The router does adapt (post-event
  +0.035 vs greedy-advertised −0.129; web_search share falls in every
  seed) but cannot reach 90% of pre-event utility: deposit clip + weak
  evaporation + lying ads (β=2) + ε floor plateau its share at
  0.10–0.20. Money plot delivered as PNG + GIF. Complete before-picture
  for the Stage-4 M6-RT backport (MMAS bounds + restarts).