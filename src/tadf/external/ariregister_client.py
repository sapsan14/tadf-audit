"""Ariregister (e-äriregister, RIK) — public-API client.

Tier 1 — Autocomplete: `https://ariregister.rik.ee/est/api/autocomplete?q=…`
  - Public, unauthenticated, free, no agreement required.
  - Accepts both name fragment and 8-digit reg-code as `q`.
  - Returns up to 10 records: name, reg_code, status, legal_address,
    legal_form (numeric code), url. No email/phone (those need tier 3).

Tier 2 — Open Data dump (avaandmed.ariregister.rik.ee, JSON/XML files
  refreshed once a day): used as offline fallback for `lookup_company`
  when the live endpoint is unreachable. Wrapper TBD; this module only
  exposes hooks (`_dump_lookup`) so a future `ariregister_dump.py` can
  plug in without changing the public API.

Tier 3 — Detailed company data query (XML services). Requires a free
  contractual customer agreement with RIK. When credentials are set
  via env (`ARIREGISTER_USERNAME`/`ARIREGISTER_PASSWORD`) we'll prefer
  this for `lookup_company` to get email/phone/capital. Without creds
  we degrade to tier 1 only.

Cache (`external/cache.py`):
  - `ariregister-autocomplete` — search hits, 7 days
  - `ariregister-detail`       — resolved company by reg-code, 30 days

The plan ("Слой 2.5 — Автономность через кэш") puts everything
offline-first: cache → live API → dump fallback → manual entry.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

from tadf.external.cache import cache_get, cache_key, cache_put

log = logging.getLogger(__name__)

_BASE_PUBLIC = "https://ariregister.rik.ee/est/api"
_USER_AGENT = "TADF-Audit/0.2 (https://github.com/sapsan14/tadf-audit)"
_TIMEOUT_S = 10.0
_SEARCH_TTL_DAYS = 7
_DETAIL_TTL_DAYS = 30


# Estonian legal-form codes from RIK. Not exhaustive — covers the forms
# the auditor sees day-to-day; unknown codes fall through to the raw value
# so we never lie about what RIK said.
_LEGAL_FORM = {
    "1": "AS",
    "5": "OÜ",
    "7": "TÜH",     # tulundusühistu
    "9": "MTÜ",     # mittetulundusühing
    "12": "FIE",    # füüsilisest isikust ettevõtja
    "28": "SA",     # sihtasutus
    "32": "RHü",    # riigihaldus
}


# Estonian status codes — `R` = registered/active is the only one we care
# about for highlighting; everything else is shown as-is.
_STATUS_LABEL = {
    "R": "активна",
    "K": "ликвидирована",
    "L": "в процессе ликвидации",
    "P": "приостановлена",
}


def _client() -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        },
        timeout=_TIMEOUT_S,
        follow_redirects=True,
    )


def _has_contract_credentials() -> bool:
    """True iff ARIREGISTER_USERNAME and ARIREGISTER_PASSWORD are both set.

    Tier-3 detailed-query is enabled at runtime by populating these. Until
    then, lookup falls back to autocomplete + (future) dump.
    """
    return bool(os.environ.get("ARIREGISTER_USERNAME")) and bool(
        os.environ.get("ARIREGISTER_PASSWORD")
    )


def is_available() -> bool:
    """Always True — autocomplete + cache let the picker function offline
    after at least one warm-up. Network failures are handled gracefully
    inside `search_company`/`lookup_company`."""
    return True


# ---------------------------------------------------------------------------
# Search — autocomplete by name fragment OR reg-code
# ---------------------------------------------------------------------------


@dataclass
class CompanyHit:
    reg_code: str
    name: str
    legal_form: str | None         # human label ("OÜ", "AS"...) — falls through
    legal_form_code: str | None    # RIK's raw numeric code
    status: str | None             # "R", "K", ...
    status_label: str | None       # human label ("активна"...)
    address: str | None            # legal_address
    zip_code: str | None
    url: str | None                # canonical e-äriregister page
    raw: dict[str, Any]


def search_company(
    query: str, *, limit: int = 10, force_refresh: bool = False
) -> list[CompanyHit]:
    """Search Ariregister by name fragment OR 8-digit reg-code.

    `limit` is advisory — RIK caps autocomplete at 10 server-side and we
    just slice the response. Empty / 1-char input returns [] without a
    network round-trip. `force_refresh` skips the local cache.
    """
    q = (query or "").strip()
    if len(q) < 2:
        return []

    cache_k = cache_key("ariregister-autocomplete", q)
    if not force_refresh:
        cached = cache_get(
            "ariregister-autocomplete", cache_k, ttl_days=_SEARCH_TTL_DAYS
        )
        if cached is not None:
            return [_hit_from_dict(d) for d in cached["hits"][:limit]]

    url = f"{_BASE_PUBLIC}/autocomplete"
    try:
        with _client() as c:
            r = c.get(url, params={"q": q})
            r.raise_for_status()
            payload = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("Ariregister autocomplete failed for %r: %s", q, e)
        return []

    if not isinstance(payload, dict) or payload.get("status") != "OK":
        log.warning("Ariregister autocomplete returned non-OK shape: %s", payload)
        return []

    raw_data = payload.get("data") or []
    hits = [h for h in (_parse_autocomplete_row(r) for r in raw_data) if h is not None]
    cache_put(
        "ariregister-autocomplete",
        cache_k,
        {"hits": [_hit_to_dict(h) for h in hits]},
    )
    return hits[:limit]


# ---------------------------------------------------------------------------
# Lookup — by exact 8-digit reg-code
# ---------------------------------------------------------------------------


def lookup_company(reg_code: str, *, force_refresh: bool = False) -> dict[str, Any] | None:
    """Resolve a company by exact reg-code.

    Source order (offline-first):
      1. Local cache (`ariregister-detail`, TTL 30d) unless `force_refresh`.
      2. Tier 3 — detailed-company-data-query (only if creds are set). TBD.
      3. Tier 1 — autocomplete row (always available, basic fields only).
      4. Tier 2 — Open Data dump fallback (TBD).
    Returns a dict shaped for the `Client` model
    (`name`/`reg_code`/`address`/`legal_form`/`status` + `email`/`phone`
    when tier 3 is available) or `None`.
    """
    code = (reg_code or "").strip()
    if not code.isdigit() or len(code) != 8:
        return None

    cache_k = cache_key("ariregister-lookup", code)
    if not force_refresh:
        cached = cache_get("ariregister-detail", cache_k, ttl_days=_DETAIL_TTL_DAYS)
        if cached is not None:
            return cached["fields"]

    fields: dict[str, Any] | None = None
    if _has_contract_credentials():
        # TODO(stage 2c): wire up detailed-company-data-query once creds land.
        # Until then this stays a forward-compatible no-op so we don't
        # accidentally lock onto the (less complete) autocomplete row.
        fields = None

    if fields is None:
        hits = search_company(code, limit=1, force_refresh=force_refresh)
        if hits:
            fields = _hit_to_client_fields(hits[0])

    # Tier 2 dump fallback — currently a no-op stub. The hook is here so
    # `_dump_lookup` can be filled in by a follow-up commit without
    # changing this module's public API.
    if fields is None:
        fields = _dump_lookup(code)

    if fields is None:
        return None

    cache_put("ariregister-detail", cache_k, {"fields": fields})
    return fields


def _dump_lookup(reg_code: str) -> dict[str, Any] | None:
    """Stage-2 hook — answer from a locally-downloaded RIK dump.

    Currently returns None (no dump). When `ariregister_dump.py` lands,
    it'll be imported lazily here so this module stays import-safe even
    without the dump dependency.
    """
    return None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_autocomplete_row(row: Any) -> CompanyHit | None:
    if not isinstance(row, dict):
        return None
    reg_raw = row.get("reg_code")
    name = (row.get("name") or "").strip()
    if not reg_raw or not name:
        return None
    reg_code = str(reg_raw).zfill(8)
    legal_form_code = str(row.get("legal_form")) if row.get("legal_form") else None
    legal_form = _LEGAL_FORM.get(legal_form_code or "", legal_form_code)
    status = (row.get("status") or "").strip() or None
    status_label = _STATUS_LABEL.get(status or "")
    return CompanyHit(
        reg_code=reg_code,
        name=name,
        legal_form=legal_form,
        legal_form_code=legal_form_code,
        status=status,
        status_label=status_label,
        address=(row.get("legal_address") or "").strip() or None,
        zip_code=(row.get("zip_code") or "").strip() or None,
        url=(row.get("url") or "").strip() or None,
        raw=row,
    )


def _hit_to_client_fields(h: CompanyHit) -> dict[str, Any]:
    """Project a CompanyHit onto the `Client` model field shape."""
    out: dict[str, Any] = {
        "name": h.name,
        "reg_code": h.reg_code,
    }
    if h.address:
        out["address"] = h.address
    if h.legal_form:
        out["legal_form"] = h.legal_form
    if h.status:
        out["status"] = h.status
    return out


def _hit_to_dict(h: CompanyHit) -> dict[str, Any]:
    return {
        "reg_code": h.reg_code,
        "name": h.name,
        "legal_form": h.legal_form,
        "legal_form_code": h.legal_form_code,
        "status": h.status,
        "status_label": h.status_label,
        "address": h.address,
        "zip_code": h.zip_code,
        "url": h.url,
        "raw": h.raw,
    }


def _hit_from_dict(d: dict[str, Any]) -> CompanyHit:
    return CompanyHit(
        reg_code=d.get("reg_code") or "",
        name=d.get("name") or "",
        legal_form=d.get("legal_form"),
        legal_form_code=d.get("legal_form_code"),
        status=d.get("status"),
        status_label=d.get("status_label"),
        address=d.get("address"),
        zip_code=d.get("zip_code"),
        url=d.get("url"),
        raw=d.get("raw") or {},
    )


__all__ = [
    "CompanyHit",
    "is_available",
    "lookup_company",
    "search_company",
]
