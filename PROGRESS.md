# PROGRESS — ACO Demo-First

Legend: `[me]` = human-owned (reading / blog writing / Track B), `[agent]` =
agent-owned (code / experiments / scaffolding). Update after every milestone;
one commit + tag per milestone.

## Session 0 re-baseline (2026-10-02, charter v2+v3)
- Repo state: `main` in sync with origin; tests 87/87 pass; all three
  experiment entry points (M6.5/M6.6/M6.7) re-run cleanly from their shipped
  configs and reproduce the committed `summary.json` byte-for-byte (m6.5
  differs only by the trailing newline added post-hoc in d8e39dd). `uv lock
  --check` clean. Dependencies current (numpy 2.5.3, matplotlib 3.11.2,
  pandas 3.0.5, pyyaml 6.0.3, pytest 9.1.1).
- Docs restored in-repo from git history (charter v3: self-contained
  project): CLAUDE.md, ROADMAP.md, PROGRESS.md, docs/ (primer,
  design-searchy, diagnosis-log), blog/posts/ stubs — they had been moved to
  Notion (commits 1d2872a..2adfdbf). ROADMAP.md rewritten with charter v2+v3
  amendments; this file re-baselined.
- R1.2, R2.2, R3.2: trimmed in charter v2 for Firecrawl focus (moved to
  optional backlog).
- M3.4 (ACS), 5th TSP instance, candidate lists: dropped from Stage 3 in
  charter v2, absorbed into Stage 4 where they serve the claim. Under
  charter v3 the old M-FC milestones are replaced entirely by the FO
  overlay module — "M-FC owns improvements" is void; M7.x owns improvements.
- Proposed resume point (awaiting human approval): G6 — the 2-minute
  narratable demo + money plot. All M6.x milestones are done with honest
  results; G6 is the last open Stage 1 item before Stage 2 (reading, human)
  runs in parallel with Stage 3 (lean TSP sprint).

## Human queue — [me] (logged 2026-10-02; work whenever ready, none of it blocks the agent)

Reading (Stage 2, trimmed to 4 core items; triggers are all LIVE — logged
in docs/diagnosis-log.md):
1. **R1.1** — read Dorigo & Stützle ch.1–2 (or Scholarpedia). Trigger:
   D3/D4 (stagnation, flat learning curve from query ~5). Unlocks: Post 2
   mechanics section.
2. **R2.1** — read Stützle & Hoos 2000 (MAX-MIN AS). Trigger: D5 (τ
   lock-in; sabotaged tool can't be unlearned). Unlocks: Post 3 pheromone
   bounds; feeds the M6-RT backport.
3. **R2.3** — build the variants comparison table (AS/ACS/MMAS × 6
   attributes) framed as "fixes to bugs we saw." Unlocks: Post 3
   centerpiece.
4. **R3.1** — skim AMRO-S + ACO-ToT. Unlocks: Post 2 sidebar.

Blog (Stage 6): Post 1 "I Built a Search Agent That Routes Like an Ant
Colony" — material ready: docs/demo-script.md (2-min narration),
figures/m6.6-sabotage.png + .gif (money plot), all committed results.
Outreach (TB.3) can start when Post 1 ships.

Track B (2–3h/week cap): TB.1 Firecrawl Discord presence; TB.2 1–2 small
PRs to github.com/firecrawl/firecrawl (read CONTRIBUTING.md first).

Backlog (trimmed in charter v2; revisit only if a milestone demands):
R1.2, R2.2, R3.2.

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
- [x] [agent] M6.7 pheromone heatmaps (**DONE 2026-09-17**, tag m6.7 — 87
      tests passing. Retrieve layer visibly splits by type at every
      snapshot (factual→web_search, math→vector_db, summarization→
      knowledge_base, code→web_search; TV distance 0.15–0.17); process
      layer concentrates on small_llm for every type (argmax identical
      across types; TV 0.04–0.10 by query 100) — small_llm is genuinely
      best on 3/4 types and the D3 lock-in shows in τ (process small_llm
      13.4 vs ≤2.0). Descriptive by design, no pass/fail verdict
      manufactured; raw τ in CSVs/JSON)
- [x] [agent] G6 (GATE 1) — 2-min narratable demo + all artifacts (**DONE
      2026-10-02**, tag g6 — docs/demo-script.md: timestamped 2-minute
      narration over the committed figures (money plot + GIF, convergence,
      per-type heatmaps); every number cites seeds + protocol; one-command
      repro per experiment verified byte-for-byte)

## Stage 2 — Diagnosis-driven reading (Weeks 3–5) — [me]
Trimmed to 4 core items (charter v2); R1.2/R2.2/R3.2 → optional backlog.
- [ ] [me] R1.1 trigger seen: router stagnation/recovery → read Dorigo & Stützle ch.1–2 → unlock: Post 2 mechanics
- [ ] [me] R2.1 trigger seen: τ collapse or over-dominance → read Stützle & Hoos 2000 (MMAS) → unlock: Post 3 pheromone bounds (MMAS as fix to observed bug)
- [ ] [me] R2.3 variants comparison table (AS/ACS/MMAS × 6 attributes) as "fixes to bugs we saw" → unlock: Post 3 centerpiece
- [ ] [me] R3.1 skim AMRO-S + ACO-ToT → unlock: Post 2 sidebar (honest similarities AND differences)
- [ ] [me] (backlog) R1.2 Dorigo/Maniezzo/Colorni 1996 — trimmed in charter v2
- [ ] [me] (backlog) R2.2 ACS q0/exploitation — trimmed in charter v2
- [ ] [me] (backlog) R3.2 DyNACO anti-stagnation — trimmed in charter v2

## Stage 3 — Lean TSP validation sprint (~1 week) — [agent]
- [x] [agent] M0.2 TSPLIB loader (EUC_2D: eil51, berlin52, eil101) (**DONE
      2026-10-02**, tag m0.2 — src/searchy/tsp.py: strict EUC_2D parser,
      TSPLIB's rounded-Euclidean convention d=floor(√(dx²+dy²)+0.5) (Reinelt),
      known optima {eil51: 426, berlin52: 7542, eil101: 629}; instances
      downloaded verbatim into data/tsplib/ (Heidelberg's official server
      returns an HTML "not available" page; used the mastqe/tsplib GitHub
      mirror — dimensions + EUC_2D headers verified, optima checked via NN
      landscape). 19 new tests)
- [x] [agent] M0.3 nearest-neighbor baseline (**DONE 2026-10-02**, tag m0.2
      — best-of-all-starts NN: eil51 482 (+13.15% — inside the roadmap's
      426±15% anchor), berlin52 8181 (+8.47%), eil101 746 (+18.60%).
      Measured note: eil101's best NN misses the 15% band — that is the
      instance's rougher NN landscape (mean gap +32.3%), not a loader bug;
      test ceilings set per-instance with the numbers cited. Mean NN gaps
      23.2/24.3/32.3%)
- [ ] [agent] M3.1 AS from scratch on eil51 — median gap <8% over 10 seeds
- [ ] [agent] M3.5 MMAS + restarts — diversity ≠ 0 for 50 consecutive iterations across 500
- [ ] [agent] M3.6 2-opt refinement + runtime-share measurement
- [ ] [agent] M4-L runner + metrics + Wilcoxon → ONE table: AS vs MMAS ± 2-opt, 3 instances × 30 seeds, equal construction budget — GATE: one-command reproducibility
- [ ] [agent] minimal viz: one convergence plot + one pheromone heatmap

## Stage 4 — Improvements, proven (Weeks 6–8)
- [ ] [agent] M7.1 NN-tour pheromone init vs uniform τ0 (3 × 30)
- [ ] [agent] M7.2 stagnation restart OR adaptive ρ (same protocol)
- [ ] [agent] M7.3 candidate lists k=20 on largest instance
- [ ] [agent] M7.4 combined improved-AS vs AS and MMAS+2-opt, p-values — GATE: "X improved Y by Z% (p<0.05, n=30)"
- [ ] [agent] M7.5 honest negative-results log
- [ ] [agent] M6-RT backport MMAS bounds + restart to Searchy; re-run M6.5/M6.6; before/after plots

## Stage 5 — Firecrawl Overlay (~2 days, after Stage 4) — [agent]
Human credit approval REQUIRED before FO.1. Doc > demo; cut at 2 days.
- [ ] [agent] FO.1 fixture record (~25 queries × 5 tool calls, ONCE, ≤$15 credits) → deterministic 30-seed replay
- [ ] [agent] FO.2 overlay demo plot (traffic share + cumulative credit spend, one adaptation moment) — one figure
- [ ] [agent] FO.3 docs/firecrawl-overlay.md — mapping table: ACO mechanism → Firecrawl search problem → what I'd do differently at their scale

## Stage 6 — Blog arc — [me] writes
- [x] [agent] Scaffold blog/posts/ stubs (done at kickoff; restored in-repo 2026-10-02)
- [ ] [me] Post 1 (~W3): "I Built a Search Agent That Routes Like an Ant Colony"
- [ ] [me] Post 2 (~W4): "How ACO Actually Works — Explained by a System I Built First"
- [ ] [me] Post 3 (~W5): "Everything I Got Wrong, the Literature Knew by 2000"
- [ ] [me] Post 4 (~W6): "I Benchmarked My Colony on the Classic Problem" (lean TSP study)
- [ ] [me] Post 5 (~W8): "Can You Improve ACO? I Ran 30 Seeds to Find Out"
- [ ] [me] (optional) Post 6 / Post 5 final section: the Firecrawl overlay demo

## Track B — visibility (parallel, 2–3h/week cap) — [me]
- [ ] [me] TB.1 be usefully active in Firecrawl's Discord
- [ ] [me] TB.2 1–2 small merged PRs to github.com/firecrawl/firecrawl
- [ ] [me] TB.3 when Post 1 ships, share it publicly and tag them appropriately

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
- 2026-10-02: Charter v2 + v3 applied (Session 0). Docs restored in-repo
  from git history after the Notion move; ROADMAP rewritten (Stage 3 =
  lean TSP sprint at 3 instances, AS + MMAS ± 2-opt only; M-FC deleted;
  FO overlay added, 2-day cap; Track B added; reading trimmed).
  Re-baseline: all Stage 1 code milestones verified DONE (tests 87/87,
  experiments reproduce byte-for-byte); G6 open; Stages 2–6 not started.
- 2026-10-02: G6 closed (tag g6). Stage 1 COMPLETE. The demo package is
  docs/demo-script.md — a timestamped 2-minute narration citing only
  committed, seed-counted numbers, over the existing figures (no new
  experiments, no new figures; all figures verified byte-identical on
  re-run). Stage 1's honest record: M6.5 split negative, M6.6 negative,
  M6.7 descriptive — the failures are logged and are the Stage-2 reading
  triggers and Stage-4 before-pictures, per the demo-first bet.
- 2026-10-02: Human queue logged at the top of this file (reading R1.1,
  R2.1, R2.3, R3.1 with live triggers; Post 1 material ready; Track B).
  M0.2+M0.3 closed (tag m0.2). Heidelberg's TSPLIB server is dead
  (returns an HTML "not available" page — NOT instance data); instances
  fetched from the mastqe/tsplib GitHub mirror and verified against
  published optima via the NN landscape. eil101's best-of-all-starts NN
  is +18.60% over optimum — outside the eil51-style ±15% band; logged as
  a measured instance property (its mean NN gap is +32.3%), not tuned or
  hidden. Loader enforces TSPLIB's rounded-EUC_2D (floor(d+0.5)) — the
  float-distance version would shift eil51's optimum by ~0.4%.