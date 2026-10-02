# G6 — The 2-Minute Demo (Stage 1 narration script)

Implements G6 (ROADMAP GATE 1): "2-minute narratable demo + all artifacts."

Everything shown is measured, seed-counted, and reproducible with one
command per experiment (configs and results live in `experiments/`;
protocol details in each `summary.json`). Numbers cite 5 seeds, one shared
100-query stream, M6.3 parameters verbatim — nothing tuned anywhere in
Stage 1. Run the demo from the repo root:

```bash
uv run pytest                                              # 87/87 pass
uv run python -m searchy.experiment experiments/configs/m6.5-comparison.yaml
uv run python -m searchy.sabotage   experiments/configs/m6.6-sabotage.yaml
uv run python -m searchy.heatmaps  experiments/configs/m6.7-heatmaps.yaml
```

Each command regenerates its committed results byte-for-byte.

---

## The system in one breath (0:00–0:20)

Searchy is a search agent with a tool pool of six simulated tools in two
layers — three retrieve (knowledge_base, vector_db, web_search), three
process (calculator, regex_processor, small_llm). Every query is an ant:
it picks one tool per layer with the ACO transition rule
P(tool) ∝ τ^α · η^β — pheromone learned from experience times the tool's
*advertised* skill. Two ads deliberately lie. Good paths deposit pheromone;
evaporation slowly forgets. The colony has never seen a paper; it learns
routing from nothing but realized rewards.

Artifact: `experiments/results/figures/m6.7-tau.png` — the shared 2×3
pheromone matrix growing over 100 queries.

## Claim 1 — it learns to beat the strawman (0:20–0:50)

Against four baselines on the same query stream (100 queries × 5 seeds,
M6.5): the pheromone router's cumulative reward **17.70 ± 0.71** vs
greedy-advertised — the trust-the-ads-forever strawman — **16.88 ± 0.35**;
router wins 4/5 seeds. Random sits at 13.10, cheapest at 9.14. The oracle
upper bound is 36.46, so the colony captures ~49% of the headroom over
random but only ~49% of oracle utility — the honest headline is *beats the
strawman on the cost side, still far from optimal*.

Artifact: `experiments/results/figures/m6.5-convergence.png`.

## Claim 2 — the flagship moment: it notices when the world changes (0:50–1:30)

At query #50 we sabotage web_search: true quality drops to 0.05, latency
×3 — ads unchanged. The strawman trusts the ads forever and eats the
damage: post-event mean reward **−0.129**. The colony notices through
realized rewards alone and reroutes — web_search's traffic share falls in
every seed (pre-event shares 0.58/0.55/0.24/0.36/0.24 drop to window minima
0.20/0.10/0.10/0.20/0.10), post-event mean reward **+0.035**. The oracle
re-picks instantly (+0.365).

Honest verdict, DoD NOT MET: share clause 3/5 seeds, recovery-to-90% clause
1/5 — the colony plateaus at 0.10–0.20 web_search share instead of
abandoning it (deposit clip + lying ads + ε floor; diagnosis-log D5).
The adaptation is real but insufficient — and that failure is the exact
before-picture for the Stage-4 MMAS-bounds backport.

Artifact: `experiments/results/figures/m6.6-sabotage.png` (static money
plot) and `m6.6-sabotage.gif` (the reroute, animated, vertical line at
#50).

## Claim 3 — it routes differently per query type (1:30–1:50)

Per-type effective routing (M6.7, mean over 5 seeds): factual queries go
web_search (0.42), math goes vector_db (0.38), summarization goes
knowledge_base (0.47), code goes web_search (0.43) — retrieve-layer total
variation between math and factual 0.15–0.17 at every snapshot. The
process layer honestly collapses onto small_llm for every type (τ 13.4 vs
≤2.0 by query 100): it is genuinely best on 3 of 4 types, and the lock-in
is the D3 premature-convergence pattern, logged for Stage 4.

Artifacts: `m6.7-heatmaps-retrieve.png` / `m6.7-heatmaps-process.png`
(effective probabilities) and the `-shares-` twins (realized traffic).

## The close (1:50–2:00)

What the colony did right: beat the strawman, notice sabotage, split by
query type — all from experience, zero theory given in advance. Where it
falls short is measured, not hidden: 48.6% of oracle, plateaued recovery.
Those three failures — premature convergence, lock-in, weak unlearning —
are precisely what the literature solved by 2000 (MMAS bounds, restarts),
which is exactly what Stage 2 reads and Stage 4 backports.

---

## Artifact index (all committed)

| Artifact | What it shows | Milestone |
|---|---|---|
| `figures/m6.5-convergence.png` | router vs 4 baselines, 100 queries × 5 seeds | M6.5 |
| `figures/m6.6-sabotage.png` | per-tool traffic share, sabotage at #50 (money plot) | M6.6 |
| `figures/m6.6-sabotage.gif` | the money plot, animated | M6.6 |
| `figures/m6.7-heatmaps-retrieve.png` | effective routing probabilities, retrieve layer, per type | M6.7 |
| `figures/m6.7-heatmaps-process.png` | same, process layer | M6.7 |
| `figures/m6.7-heatmaps-shares-*.png` | realized per-type traffic shares | M6.7 |
| `figures/m6.7-tau.png` | raw shared 2×3 pheromone matrix over time | M6.7 |
| `m6.5-comparison/`, `m6.6-sabotage/`, `m6.7-heatmaps/` | full records (CSV) + summaries (JSON) | all |