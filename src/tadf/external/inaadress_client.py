"""In-ADS — Estonian Address Data System (Maa-amet) client.

Public REST gazetteer at https://inaadress.maaamet.ee/inaadress/gazetteer.
Unauthenticated, soft per-IP rate limit. Address records virtually
never change once issued, so we cache aggressively (30 days for search
queries, 365 days for resolved-by-ADS-ID details) — this also makes
the picker work fully offline once the relevant addresses have been
seen at least once.

The plan ("Слой 2.5 — Автономность через кэш") explicitly puts in-ADS
in the offline-first column, alongside `external/ehr_client.py`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from tadf.external.cache import cache_get, cache_key, cache_put

_KATASTER_RE = re.compile(r"^\d{5}:\d{3}:\d{4}$")

log = logging.getLogger(__name__)

_BASE = "https://inaadress.maaamet.ee/inaadress"
_USER_AGENT = "TADF-Audit/0.2 (https://github.com/sapsan14/tadf-audit)"
_TIMEOUT_S = 10.0
_SEARCH_TTL_DAYS = 30
_LOOKUP_TTL_DAYS = 365


def _client() -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        },
        timeout=_TIMEOUT_S,
        follow_redirects=True,
    )


@dataclass
class AddressHit:
    address: str               # `pikkaadress` — full normalised form for display
    short: str | None          # `aadresstekst` — short form (city + street + nr)
    ads_id: str | None         # ADS object ID (`adr_id`/`tehn_id`) for stable refs
    kataster: str | None       # `tunnus` if returned (cadastral number)
    coords: tuple[float, float] | None  # (x, y) in L-EST97 (Estonian projection)
    raw: dict[str, Any]


def is_available() -> bool:
    """In-ADS is a public unauthenticated service — always available
    in principle. The actual `search_address`/`lookup_address` calls
    degrade gracefully on network errors, returning empty results."""
    return True


# ---------------------------------------------------------------------------
# Search — by address fragment, POI, or postal code
# ---------------------------------------------------------------------------


def search_address(query: str, *, limit: int = 10) -> list[AddressHit]:
    """Free-text search returning normalised addresses.

    Minimum 2 chars per the In-ADS spec. Empty/short input returns
    an empty list without hitting the network. Cache namespace:
    `inaadress` (TTL 30 days).
    """
    q = (query or "").strip()
    if len(q) < 2:
        return []

    cache_k = cache_key("inaadress-search", q, str(limit))
    cached = cache_get("inaadress", cache_k, ttl_days=_SEARCH_TTL_DAYS)
    if cached is not None:
        return [_hit_from_dict(d) for d in cached["hits"]]

    url = f"{_BASE}/gazetteer"
    params = {
        "address": q,
        "results": str(limit),
        "appartment": "0",
        "results_only": "1",
    }
    try:
        with _client() as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("In-ADS search failed for %r: %s", q, e)
        return []

    raw_hits = _extract_hit_array(data)
    hits = [h for h in (_parse_address(a) for a in raw_hits) if h is not None]
    cache_put("inaadress", cache_k, {"hits": [_hit_to_dict(h) for h in hits]})
    return hits


def lookup_address(ads_id: str, *, force_refresh: bool = False) -> AddressHit | None:
    """Resolve a single canonical address by ADS-ID.

    `force_refresh=True` skips the long-TTL cache. Cache namespace:
    `inaadress-detail` (TTL 365 days — addresses change rarely once
    canonicalised).
    """
    aid = (ads_id or "").strip()
    if not aid:
        return None

    cache_k = cache_key("inaadress-lookup", aid)
    if not force_refresh:
        cached = cache_get("inaadress-detail", cache_k, ttl_days=_LOOKUP_TTL_DAYS)
        if cached is not None:
            return _hit_from_dict(cached["hit"])

    url = f"{_BASE}/gazetteer"
    params = {"adsid": aid, "appartment": "0", "results_only": "1"}
    try:
        with _client() as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("In-ADS lookup failed for %s: %s", aid, e)
        return None

    raw_hits = _extract_hit_array(data)
    if not raw_hits:
        return None
    hit = _parse_address(raw_hits[0])
    if hit is None:
        return None
    cache_put("inaadress-detail", cache_k, {"hit": _hit_to_dict(hit)})
    return hit


# ---------------------------------------------------------------------------
# Parsing — In-ADS returns a JSON envelope; the array key has historically
# varied (`addresses`, `tulemused`). We probe in order and skip non-dicts.
# ---------------------------------------------------------------------------


_HIT_ARRAY_KEYS = ("addresses", "tulemused", "results")


def _extract_hit_array(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [a for a in data if isinstance(a, dict)]
    if not isinstance(data, dict):
        return []
    for k in _HIT_ARRAY_KEYS:
        v = data.get(k)
        if isinstance(v, list):
            return [a for a in v if isinstance(a, dict)]
    return []


def _parse_address(a: dict[str, Any]) -> AddressHit | None:
    address = (
        a.get("pikkaadress")
        or a.get("ipikkaadress")
        or a.get("aadresstekst")
        or ""
    )
    address = address.strip() if isinstance(address, str) else ""
    if not address:
        return None
    short = a.get("aadresstekst")
    ads_id = a.get("adr_id") or a.get("ads_oid") or a.get("tehn_id")
    # Kataster only counts when the string matches the canonical
    # Estonian cadastral format `XXXXX:XXX:XXXX`. In-ADS sometimes
    # returns an internal numeric ID under `tunnus` for non-cadastral
    # objects (apartments, points-of-interest), and we don't want
    # those leaking into Building.kataster_no.
    kat_raw = a.get("ky_tunnus") or a.get("tunnus")
    kataster = (
        str(kat_raw) if kat_raw and _KATASTER_RE.match(str(kat_raw)) else None
    )

    coords: tuple[float, float] | None = None
    try:
        x = a.get("viitepunkt_x") or a.get("x")
        y = a.get("viitepunkt_y") or a.get("y")
        if x is not None and y is not None:
            coords = (float(x), float(y))
    except (TypeError, ValueError):
        coords = None

    return AddressHit(
        address=address,
        short=short if isinstance(short, str) and short.strip() else None,
        ads_id=str(ads_id) if ads_id else None,
        kataster=str(kataster) if kataster else None,
        coords=coords,
        raw=a,
    )


def _hit_to_dict(h: AddressHit) -> dict[str, Any]:
    return {
        "address": h.address,
        "short": h.short,
        "ads_id": h.ads_id,
        "kataster": h.kataster,
        "coords": list(h.coords) if h.coords else None,
        "raw": h.raw,
    }


def _hit_from_dict(d: dict[str, Any]) -> AddressHit:
    coords = d.get("coords")
    return AddressHit(
        address=d.get("address") or "",
        short=d.get("short"),
        ads_id=d.get("ads_id"),
        kataster=d.get("kataster"),
        coords=tuple(coords) if isinstance(coords, list) and len(coords) == 2 else None,
        raw=d.get("raw") or {},
    )


__all__ = [
    "AddressHit",
    "is_available",
    "lookup_address",
    "search_address",
]
