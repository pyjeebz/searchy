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
      (human approval → **pending**)
- [ ] [me]   R0.1 gate — read primer, pass from-memory test
- [ ] [agent] M6.2 queries.py + tools.py
- [ ] [agent] M6.3 router.py (ACO core)
- [ ] [agent] M6.4 baselines.py
- [ ] [agent] M6.5 comparison experiment (100 queries × 5 seeds)
- [ ] [agent] M6.6 sabotage demo (money plot + GIF)
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