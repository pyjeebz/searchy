# R0.1 — ACO Crash Primer (for the Searchy router)

Implements R0.1. Exactly five things, no more. Your gate: after reading this,
you should be able to write the transition rule and the update equation from
memory.

---

## 1. Stigmergy

Stigmergy is indirect coordination through the environment: an agent modifies
the world (e.g., deposits a chemical), and later agents sense that
modification and change their behavior because of it. No agent talks to any
other agent; the *environment is the memory*. Ant colonies use pheromone
trails this way — a trail to good food gets reinforced by every ant that
follows it and finds food, and fades when it stops paying off. Searchy does
the same thing with numbers: the "environment" is a pheromone matrix over
tools, and the "ants" never communicate except by leaving traces in it.

## 2. The transition rule (how an ant picks the next tool)

For a query ("ant") currently at layer `l`, the probability of choosing
tool `j` is:

```
P(tool_j | layer l, query q)  ∝  τ[l][j]^α  ·  η[j,q]^β
```

- `τ[l][j]` — **pheromone** on tool `j` at layer `l`: the colony's accumulated,
  evaporating *experience* that this tool has been worth using here.
- `η[j,q]` — **heuristic desirability**: tool `j`'s *advertised* skill match
  for query `q`'s type. In Searchy this is noisy and, for 1–2 tools,
  deliberately misleading. The colony must learn to trust or distrust it.
- `α` — how much to weight experience (start: **1**).
- `β` — how much to weight the advertisement (start: **2**).
- "∝" means normalize: divide by the sum over all candidate tools in the layer
  so the probabilities sum to 1.

High `β` relative to `α` means "trust ads at first"; pheromone accumulates over
time and can override a bad ad.

## 3. The pheromone update (applied per query batch)

Every batch (10 queries), first **evaporate**, then **deposit**:

```
τ ← (1 − ρ) · τ                  (evaporation, whole matrix)
τ[l][j] += Q · R(path)           (deposit, only for edges/tools the query used)
```

- `ρ` (start: **0.05**) — evaporation rate: old evidence decays, so stale tool
  quality gets forgotten.
- `Q` (start: **1**) — deposit scale.
- `R(path)` (start: reward-weighted deposit) — the query's reward (quality of
  the path minus cost/latency penalty). Better paths leave stronger traces.
  Only the tools the query actually used get the deposit — that's the
  reinforcement signal: *use it, get rewarded, others follow*.

## 4. Exploration safeguard

With probability `ε` (start: **0.1**) a query ignores the transition rule and
picks a **uniformly random** tool in the layer. This keeps a floor of
experimentation alive so a tool that got a bad start (or was sabotaged after
being good) can still be re-sampled and re-discovered. Without it, pheromone
can lock the colony onto a choice forever.

## 5. Mapping table: ACO concept → Searchy equivalent

| ACO concept | Searchy equivalent |
|---|---|
| ants | queries (each query walks layer 1 → layer 2) |
| graph / solution construction | the 2-layer tool pool (3 retrieve tools → 3 process tools) |
| pheromone τ | per-layer tool preferences, persisted across queries |
| heuristic η | each tool's *advertised* skill match per query type (noisy, possibly wrong) |
| evaporation | forgetting stale tool quality (a tool that stops being good decays) |
| deposit | rewarding good paths so future queries follow them |

---

## Starting parameters (recap)

`α=1, β=2, ρ=0.05, ε=0.1, Q=1`, reward-weighted deposit, evaporation per
batch of 10 queries.

**Gate check (for you, the human):** without looking, write down
(1) the transition rule and (2) the update equation, with the meaning of each
symbol. If you can, we start coding.