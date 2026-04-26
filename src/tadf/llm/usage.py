"""Track Anthropic token usage + estimated cost across sessions.

Usage is appended to a JSONL file at `data/cache/llm/usage.jsonl` so the
counter survives Streamlit restarts and isn't lost between days. Aggregation
is fast — there's no expectation of millions of rows for a one-person practice.

Pricing per million tokens (USD), cached 2026-04 from the public price list:
  - claude-sonnet-4-6: $3.00 input / $15.00 output
  - claude-haiku-4-5:  $1.00 input / $5.00 output

Cache reads are ~10 % of input price; cache writes are ~125 % of input price
(both for the 5-minute TTL we use).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from tadf.config import CACHE_DIR

USAGE_LOG = CACHE_DIR / "llm" / "usage.jsonl"
USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)

# USD per million tokens
PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-opus-4-7": {"input": 5.00, "output": 25.00},
}
CACHE_READ_FACTOR = 0.10  # read tokens = 10 % of input price
CACHE_WRITE_FACTOR = 1.25  # write tokens = 125 % of input price (5-min TTL)


@dataclass(frozen=True)
class UsageRow:
    ts: float
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int

    @property
    def cost_usd(self) -> float:
        p = PRICING.get(self.model)
        if not p:
            return 0.0
        cost = (
            self.input_tokens * p["input"]
            + self.output_tokens * p["output"]
            + self.cache_read_tokens * p["input"] * CACHE_READ_FACTOR
            + self.cache_write_tokens * p["input"] * CACHE_WRITE_FACTOR
        ) / 1_000_000
        return round(cost, 6)


def record(model: str, usage: Any) -> None:
    """Persist one API call's usage to the JSONL log.

    `usage` is the `response.usage` object from anthropic.types. Tolerates
    missing attributes (older SDK shapes return None for cache fields).
    """
    row = UsageRow(
        ts=time.time(),
        model=model,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
    )
    with USAGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row.__dict__) + "\n")


def read_all() -> list[UsageRow]:
    if not USAGE_LOG.exists():
        return []
    rows: list[UsageRow] = []
    for line in USAGE_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            rows.append(UsageRow(**d))
        except Exception:
            continue
    return rows


@dataclass(frozen=True)
class Summary:
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    by_model: dict[str, dict[str, float]]


def summarise() -> Summary:
    rows = read_all()
    by_model: dict[str, dict[str, float]] = {}
    total = {
        "calls": 0,
        "input": 0,
        "output": 0,
        "cache_read": 0,
        "cache_write": 0,
        "cost": 0.0,
    }
    for r in rows:
        m = by_model.setdefault(
            r.model,
            {"calls": 0, "input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "cost": 0.0},
        )
        m["calls"] += 1
        m["input"] += r.input_tokens
        m["output"] += r.output_tokens
        m["cache_read"] += r.cache_read_tokens
        m["cache_write"] += r.cache_write_tokens
        m["cost"] += r.cost_usd
        total["calls"] += 1
        total["input"] += r.input_tokens
        total["output"] += r.output_tokens
        total["cache_read"] += r.cache_read_tokens
        total["cache_write"] += r.cache_write_tokens
        total["cost"] += r.cost_usd
    return Summary(
        calls=int(total["calls"]),
        input_tokens=int(total["input"]),
        output_tokens=int(total["output"]),
        cache_read_tokens=int(total["cache_read"]),
        cache_write_tokens=int(total["cache_write"]),
        cost_usd=round(total["cost"], 4),
        by_model={
            k: {kk: round(vv, 4) if kk == "cost" else vv for kk, vv in v.items()} for k, v in by_model.items()
        },
    )


def reset() -> None:
    USAGE_LOG.unlink(missing_ok=True)
