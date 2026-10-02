# The Firecrawl Overlay — ACO mechanism → credit-aware search problem

Implements FO.3 (charter v3): the mapping table — interview prep +
application attachment. Product framing per charter v2: every row is
stated as a cost/quality lever on Firecrawl's real API.

## The one-paragraph version

Firecrawl's search/extract stack already routes: `/search` decides
where to look, `/map` decides how deep a site is worth walking,
`/scrape` decides what to pull and in which format. Every one of those
decisions costs credits and latency, and the right answer depends on
what the query actually is (docs lookup vs. news vs. structured product
data). Searchy is a proof that *routing itself can be learned online
from realized rewards* — with pheromones, so the router adapts when a
source degrades, without a model retrain. The overlay demo runs the
colony on recorded Firecrawl calls: same credit meter, same latency
profile, deterministic replay.

## Mapping table

| ACO mechanism (as built & measured here) | Firecrawl search problem | What I'd do differently at their scale |
|---|---|---|
| Ant = one query walking tool layers | One query walking /search → /scrape(markdown or json) → optional /extract | Keep it: per-query routing is exactly the unit Firecrawl bills credits on |
| Pheromone τ per (layer, tool) | A per-(query-type, endpoint) preference score, persisted per customer or globally | Store as feature weights keyed by query embedding bucket — τ is just a table; at scale it's a learned cache with the same update rule |
| Advertised skill η (noisy, sometimes lying ads) | Endpoint/format metadata: "this site is scrapeable", "json available" — known to be unreliable | Keep the ε-exploration floor: trust metadata ~90%, sample ~10%; it's what saved the colony from the lying ads (D2/D5) and it bounds worst-case credit waste |
| Deposit Q·R after each query | Credit-weighted reward: judged answer quality − λ·(credits + latency) | Firecrawl has the ground truth already: response success/failure, status codes, wall-clock — start with those before adding an LLM judge |
| Evaporation (forgetting stale quality) | Sites change scrapeability weekly; a route that worked yesterday 404s today | Same role as cache TTL, but proportional rather than binary; ρ is the "how fast do we distrust old experience" knob |
| MMAS bounds [τ_min, τ_max] (the Stage-4 fix) | Preventing one popular endpoint from permanently capturing traffic after a lucky streak | The measured before/after (M6-RT backport) is the argument: bounded pheromone is what let the colony unlearn a collapsed tool |
| Stagnation restart | Query mix drifts (new domains, new formats); router plateaus on the old mix | Restart ≈ periodic re-exploration budget; cheap to implement, the failure mode without it is measured (D3) |
| Sabotage = source degraded mid-stream | A site breaks / an endpoint's cost changes — happens constantly in their telemetry | The money demo: traffic reroutes within ~[N] queries from realized rewards alone, no retrain, no redeploy |

## Why this is defensible, not vibes

- The routing claim is first proven on canonical benchmarks (TSP table,
  30 seeds, p-values, one-command repro) — the algorithm's behavior is
  characterized where ground truth is published.
- The Firecrawl overlay replays recorded fixtures: credit costs,
  latencies, and responses are the real API's, captured once
  (≤$15, human-approved); every experiment number replays for free and
  is deterministic.
- Honest negatives are part of the record: the Searchy log (D1–D7)
  includes measured failures of exactly the mechanisms this doc
  proposes to port — and the Stage-4 fixes that address them.

## What the demo deliberately does NOT claim

- Not claiming ACO beats learned ranking models at web scale. The
  claim is narrower and measured: *online, reward-driven tool routing
  adapts to cost/quality changes faster than static routing, at bounded
  credit overhead, on real API fixtures.*
- The overlay is a ~25-query fixture set, not a production dataset —
  it demonstrates the mechanism and the harness, sized for honesty.