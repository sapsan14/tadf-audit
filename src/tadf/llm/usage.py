"""Track Anthropic token usage + estimated cost across sessions.

Persisted in the `llm_usage` SQLite table — survives deploys and
container restarts (the DB file is in the persistent `tadf-data`
volume on Hetzner). Earlier versions used a JSONL log in
`data/cache/llm/usage.jsonl`; we keep a one-time import on first
DB read so historical data is preserved.

Pricing per million tokens (USD), cached 2026-04 from the public price list:
  - claude-sonnet-4-6: $3.00 input / $15.00 output
  - claude-haiku-4-5:  $1.00 input / $5.00 output

Cache reads are ~10% of input price; cache writes are ~125% of input price
(both for the 5-minute TTL we use).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from tadf.config import CACHE_DIR
from tadf.db.orm import LlmUsageRow
from tadf.db.session import session_scope

LEGACY_JSONL = CACHE_DIR / "llm" / "usage.jsonl"
_MIGRATED_FLAG = CACHE_DIR / "llm" / ".usage_migrated"

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


def _cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
) -> float:
    p = PRICING.get(model)
    if not p:
        return 0.0
    cost = (
        input_tokens * p["input"]
        + output_tokens * p["output"]
        + cache_read_tokens * p["input"] * CACHE_READ_FACTOR
        + cache_write_tokens * p["input"] * CACHE_WRITE_FACTOR
    ) / 1_000_000
    return round(cost, 6)


def _migrate_jsonl_once() -> None:
    """Best-effort: import any pre-DB JSONL log into llm_usage, then mark
    it migrated. Runs on first read after the schema upgrade."""
    if _MIGRATED_FLAG.exists() or not LEGACY_JSONL.exists():
        return
    try:
        rows: list[dict] = []
        for line in LEGACY_JSONL.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if rows:
            with session_scope() as s:
                for r in rows:
                    s.add(
                        LlmUsageRow(
                            ts=datetime.utcfromtimestamp(r.get("ts", time.time())),
                            model=r.get("model", "unknown"),
                            input_tokens=int(r.get("input_tokens", 0)),
                            output_tokens=int(r.get("output_tokens", 0)),
                            cache_read_tokens=int(r.get("cache_read_tokens", 0)),
                            cache_write_tokens=int(r.get("cache_write_tokens", 0)),
                        )
                    )
        _MIGRATED_FLAG.parent.mkdir(parents=True, exist_ok=True)
        _MIGRATED_FLAG.write_text(f"migrated {len(rows)} rows at {time.time()}\n")
    except Exception:
        # Migration is best-effort — don't crash the app over the legacy log.
        pass


def record(model: str, usage: Any) -> None:
    """Persist one API call's usage to the DB.

    `usage` is the `response.usage` object from anthropic.types. Tolerates
    missing attributes (older SDK shapes return None for cache fields).
    """
    with session_scope() as s:
        s.add(
            LlmUsageRow(
                ts=datetime.utcnow(),
                model=model,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            )
        )


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
    """Aggregate all rows in llm_usage into per-model + total counters."""
    _migrate_jsonl_once()

    with session_scope() as s:
        # Totals
        total_row = s.execute(
            select(
                func.count(LlmUsageRow.id),
                func.coalesce(func.sum(LlmUsageRow.input_tokens), 0),
                func.coalesce(func.sum(LlmUsageRow.output_tokens), 0),
                func.coalesce(func.sum(LlmUsageRow.cache_read_tokens), 0),
                func.coalesce(func.sum(LlmUsageRow.cache_write_tokens), 0),
            )
        ).one()
        # Per-model
        model_rows = s.execute(
            select(
                LlmUsageRow.model,
                func.count(LlmUsageRow.id),
                func.coalesce(func.sum(LlmUsageRow.input_tokens), 0),
                func.coalesce(func.sum(LlmUsageRow.output_tokens), 0),
                func.coalesce(func.sum(LlmUsageRow.cache_read_tokens), 0),
                func.coalesce(func.sum(LlmUsageRow.cache_write_tokens), 0),
            ).group_by(LlmUsageRow.model)
        ).all()

    total_calls, total_in, total_out, total_cr, total_cw = total_row
    total_cost = _cost_usd(
        "_total", int(total_in), int(total_out), int(total_cr), int(total_cw)
    )
    # The above is wrong — different models have different prices.
    # Recompute by summing per-model costs.
    by_model: dict[str, dict[str, float]] = {}
    total_cost = 0.0
    for model, calls, ti, to, cr, cw in model_rows:
        cost = _cost_usd(model, int(ti), int(to), int(cr), int(cw))
        by_model[model] = {
            "calls": int(calls),
            "input": int(ti),
            "output": int(to),
            "cache_read": int(cr),
            "cache_write": int(cw),
            "cost": round(cost, 4),
        }
        total_cost += cost

    return Summary(
        calls=int(total_calls),
        input_tokens=int(total_in),
        output_tokens=int(total_out),
        cache_read_tokens=int(total_cr),
        cache_write_tokens=int(total_cw),
        cost_usd=round(total_cost, 4),
        by_model=by_model,
    )


def reset() -> None:
    """Delete every llm_usage row. Used by tests."""
    with session_scope() as s:
        s.query(LlmUsageRow).delete()


def read_all() -> list[UsageRow]:
    """Backward-compat: return UsageRow dataclasses from the DB. Tests use this."""
    _migrate_jsonl_once()
    with session_scope() as s:
        rows = s.query(LlmUsageRow).order_by(LlmUsageRow.ts).all()
        return [
            UsageRow(
                ts=r.ts.timestamp() if isinstance(r.ts, datetime) else float(r.ts),
                model=r.model,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                cache_read_tokens=r.cache_read_tokens,
                cache_write_tokens=r.cache_write_tokens,
            )
            for r in rows
        ]


# Streamlit Cloud has ephemeral storage — on Cloud the DB resets each
# restart anyway, so persisting in SQLite vs JSONL makes no difference
# there. On Hetzner the SQLite file lives in a Docker volume that survives
# restarts and image rebuilds; that's where the long-running counter lives.

# Keep `Path` import unused from oss; ruff will flag it if we leave a
# truly unused import — silence by referencing it once.
_ = Path
