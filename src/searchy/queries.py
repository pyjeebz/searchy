"""Synthetic query generation for Searchy.

Implements M6.2.

100 queries = 4 types x 25, each with a synthetic payload string. Generation
is driven entirely by the passed ``np.random.Generator``: the same seed
produces the same 100 queries in the same order.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

import numpy as np

N_QUERY_TYPES = 4
N_PER_TYPE = 25
N_QUERIES = N_QUERY_TYPES * N_PER_TYPE


class QueryType(str, Enum):
    """The four synthetic query categories."""

    FACTUAL = "factual-lookup"
    MATH = "math-calculation"
    SUMMARIZATION = "text-summarization"
    CODE = "code-snippet"


@dataclass(frozen=True)
class Query:
    """One synthetic query: a type tag plus a payload string."""

    qtype: QueryType
    payload: str


# ---------------------------------------------------------------------------
# Payload generators. Purely synthetic strings; parameters drawn from the
# passed generator so payloads vary within a type but are seed-stable.
# ---------------------------------------------------------------------------

def _ordinal(n: int) -> str:
    """1st/2nd/3rd/4th... for small synthetic ordinals."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


_FACTUAL_TEMPLATES: tuple[Callable[[np.random.Generator], str], ...] = (
    lambda rng: f"what is the {_ordinal(int(rng.integers(1, 119)))} element in the periodic table",
    lambda rng: f"who wrote the novel published in {rng.integers(1813, 2023)}",
    lambda rng: f"what is the population of {rng.choice(['Ruritania', 'Grand Fenwick', 'Opar', 'Lilliput'])}",
    lambda rng: f"in what year was the treaty of {rng.choice(['Alderaan', 'Endor', 'Naboo'])} signed",
    lambda rng: f"what is the melting point of {rng.choice(['unobtanium', 'vibranium', 'adamantium'])}",
)

_MATH_TEMPLATES: tuple[Callable[[np.random.Generator], str], ...] = (
    lambda rng: f"compute {rng.integers(11, 99)}*{rng.integers(11, 99)}+{rng.integers(1, 99)}",
    lambda rng: f"compute ({rng.integers(11, 99)}+{rng.integers(11, 99)})*{rng.integers(2, 19)}",
    lambda rng: f"compute {rng.integers(2, 99)}^{rng.integers(2, 9)} mod {rng.integers(7, 97)}",
    lambda rng: f"compute {rng.integers(1000, 9999)}/{rng.integers(2, 99)} rounded to 4 decimals",
)

_SUMMARIZATION_TEMPLATES: tuple[Callable[[np.random.Generator], str], ...] = (
    lambda rng: (
        f"summarize the following {rng.integers(400, 3000)}-word passage "
        f"about {rng.choice(['quantum computing', 'medieval trade routes', 'coral reefs'])} "
        f"in {rng.integers(2, 7)} bullet points"
    ),
    lambda rng: (
        f"condense this {rng.choice(['earnings call', 'podcast', 'lecture'])} transcript "
        f"({rng.integers(30, 180)} minutes) into a {rng.integers(50, 250)}-word brief"
    ),
    lambda rng: (
        f"tldr a {rng.choice(['white paper', 'grant proposal', 'insurance policy'])} "
        f"on {rng.choice(['battery chemistry', 'urban traffic', 'desert agriculture'])} "
        f"for a {rng.choice(['child', 'domain expert', 'busy executive'])}"
    ),
)

_CODE_TEMPLATES: tuple[Callable[[np.random.Generator], str], ...] = (
    lambda rng: f"write a function returning the {rng.integers(5, 40)}th fibonacci number",
    lambda rng: f"write a function that checks if a {rng.integers(3, 9)}-digit number is a palindrome",
    lambda rng: (
        f"parse a log line matching [{rng.choice(['ERROR', 'WARN', 'INFO'])}] "
        f"and extract the {rng.choice(['timestamp', 'status code', 'thread id'])}"
    ),
    lambda rng: f"write a function that deduplicates a list of {rng.integers(10, 10000)} records by id",
)

_PAYLOAD_GENERATORS: dict[QueryType, tuple[Callable[[np.random.Generator], str], ...]] = {
    QueryType.FACTUAL: _FACTUAL_TEMPLATES,
    QueryType.MATH: _MATH_TEMPLATES,
    QueryType.SUMMARIZATION: _SUMMARIZATION_TEMPLATES,
    QueryType.CODE: _CODE_TEMPLATES,
}


def _make_payload(qtype: QueryType, rng: np.random.Generator) -> str:
    """Draw one synthetic payload for the given query type."""
    templates = _PAYLOAD_GENERATORS[qtype]
    idx = int(rng.integers(0, len(templates)))
    return templates[idx](rng)


def generate_queries(rng: np.random.Generator, n_per_type: int = N_PER_TYPE) -> list[Query]:
    """Generate the query stream.

    Implements M6.2. Produces ``4 * n_per_type`` queries (25 per type by
    default), interleaved by a seeded shuffle so the stream order is also
    deterministic. Same generator state (same seed) => same queries, same
    order.
    """
    queries: list[Query] = []
    for qtype in QueryType:
        for _ in range(n_per_type):
            queries.append(Query(qtype=qtype, payload=_make_payload(qtype, rng)))
    order = rng.permutation(len(queries))
    return [queries[int(i)] for i in order]