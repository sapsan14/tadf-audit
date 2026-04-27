"""Public-API client for ehr.ee (Ehitisregister).

Two endpoints, both unauthenticated and CDN-cached, callable directly
from Hetzner without any browser involvement:

  GET /api/geoinfo/v1/getgeoobjectsbyaddress?address=<query>
      → list of matches; each match has object_code (EHR code),
        object_address, object_name (use purpose), kataster (in the
        sibling KAYK feature). Used for free-text / EHR-code search.

  GET /api/building/v3/buildingData?ehr_code=<code>
      → full building JSON with technical data: footprint, height,
        volume, storeys, construction year, address, kataster.

Discovered by reading the e-ehitus React-app config + sniffing the
public detailsearch SPA's network traffic. Verified against the real
production endpoint with a corpus building (#102032773, Linna AÜ 1062).

Fields that EHR does NOT expose (must come from the project document
itself, not the registry):
  - fire_class (tulepüsivusklass)
  - designer (projekteerija)
  - builder (ehitaja)
  - last_renovation_year (might be in renogiid; not pulled here)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from tadf.external.cache import cache_get, cache_key, cache_put

log = logging.getLogger(__name__)

_BASE = "https://livekluster.ehr.ee"
_USER_AGENT = "TADF-Audit/0.2 (https://github.com/sapsan14/tadf-audit)"
_TIMEOUT_S = 12.0
_TTL_DAYS = 30  # buildings change rarely


def _client() -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        },
        timeout=_TIMEOUT_S,
        follow_redirects=True,
    )


# ---------------------------------------------------------------------------
# Search — by address fragment OR EHR code
# ---------------------------------------------------------------------------


@dataclass
class EhrSearchHit:
    ehr_code: str | None  # EHR code (None for non-building features e.g. cadastres)
    address: str | None
    use_purpose: str | None  # object_name in EHR ("Suvila", "Eluhoone"...)
    object_type: str  # "EHR_KOOD" for buildings, "KAYK" for cadastres, etc.
    kataster_no: str | None  # set when object_type == KAYK
    raw: dict[str, Any]


def search_ehr(query: str) -> list[EhrSearchHit]:
    """Free-text search: address fragment, EHR code, or kataster number.

    Returns up to ~10 hits. The hit list often contains both the building
    feature (object_type='EHR_KOOD') and the cadastral feature
    (object_type='KAYK') for the same place — we return both so the
    caller can promote kataster onto the building.
    """
    q = (query or "").strip()
    if not q:
        return []

    cache_k = cache_key("ehr-search", q)
    cached = cache_get("ehr", cache_k, ttl_days=_TTL_DAYS)
    if cached is not None:
        return [_search_hit_from_dict(d) for d in cached["hits"]]

    url = f"{_BASE}/api/geoinfo/v1/getgeoobjectsbyaddress"
    try:
        with _client() as c:
            r = c.get(url, params={"address": q})
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("EHR search failed for %r: %s", q, e)
        return []

    if not isinstance(data, list):
        return []

    hits = [_parse_search_feature(f) for f in data]
    hits = [h for h in hits if h is not None]
    cache_put("ehr", cache_k, {"hits": [_search_hit_to_dict(h) for h in hits]})
    return hits


def _parse_search_feature(feature: dict[str, Any]) -> EhrSearchHit | None:
    if not isinstance(feature, dict):
        return None
    props = feature.get("properties") or {}
    obj_type = props.get("object_type") or ""
    return EhrSearchHit(
        ehr_code=props.get("object_code") if obj_type == "EHR_KOOD" else None,
        address=props.get("object_address"),
        use_purpose=props.get("object_name"),
        object_type=obj_type,
        kataster_no=props.get("object_code") if obj_type == "KAYK" else None,
        raw=props,
    )


def _search_hit_to_dict(h: EhrSearchHit) -> dict[str, Any]:
    return {
        "ehr_code": h.ehr_code,
        "address": h.address,
        "use_purpose": h.use_purpose,
        "object_type": h.object_type,
        "kataster_no": h.kataster_no,
        "raw": h.raw,
    }


def _search_hit_from_dict(d: dict[str, Any]) -> EhrSearchHit:
    return EhrSearchHit(
        ehr_code=d.get("ehr_code"),
        address=d.get("address"),
        use_purpose=d.get("use_purpose"),
        object_type=d.get("object_type", ""),
        kataster_no=d.get("kataster_no"),
        raw=d.get("raw") or {},
    )


# ---------------------------------------------------------------------------
# Lookup — full building data by EHR code
# ---------------------------------------------------------------------------


def lookup_ehr(ehr_code: str) -> dict[str, Any] | None:
    """Return a Building-shaped dict for the given EHR code.

    Returns None if the building is not found, the API errors out, or
    the response shape is unexpected. The caller should treat None as
    "lookup failed — fall back to manual entry / browser flow".
    """
    code = (ehr_code or "").strip()
    if not code:
        return None

    cache_k = cache_key("ehr-lookup", code)
    cached = cache_get("ehr", cache_k, ttl_days=_TTL_DAYS)
    if cached is not None:
        return cached["fields"]

    url = f"{_BASE}/api/building/v3/buildingData"
    try:
        with _client() as c:
            r = c.get(url, params={"ehr_code": code})
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("EHR lookup failed for %s: %s", code, e)
        return None

    fields = map_building_data(data)
    if not fields:
        return None
    fields["ehr_code"] = code  # always set, even if not in payload
    cache_put("ehr", cache_k, {"fields": fields})
    return fields


# ---------------------------------------------------------------------------
# JSON-shape mapping — turn the EHR API response into Building fields
# ---------------------------------------------------------------------------


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).strip().replace(",", "."))
    except (ValueError, TypeError):
        return None


def _year_from_iso(iso: Any) -> int | None:
    """Extract YYYY from "1999-01-01T00:00:00.000"-style strings."""
    if not isinstance(iso, str) or len(iso) < 4:
        return None
    head = iso[:4]
    return _to_int(head)


def map_building_data(data: dict[str, Any]) -> dict[str, Any]:
    """Map the raw `/api/building/v3/buildingData` JSON to a Building dict.

    Only fields that are clearly stated in the response are included.
    Fields EHR doesn't carry (fire_class, designer, builder,
    substitute_docs_note, pre_2003) are never set here — the auditor
    fills them manually."""
    if not isinstance(data, dict):
        return {}
    ehitis = data.get("ehitis")
    if not isinstance(ehitis, dict):
        return {}

    out: dict[str, Any] = {}
    andmed = ehitis.get("ehitiseAndmed") or {}
    pohi = ehitis.get("ehitisePohiandmed") or {}
    katastrid = (
        (ehitis.get("ehitiseKatastriyksused") or {}).get("ehitiseKatastriyksus")
        or []
    )
    kehand = ehitis.get("ehitiseKehand") or {}

    # Address
    if isinstance(andmed.get("taisaadress"), str) and andmed["taisaadress"].strip():
        out["address"] = andmed["taisaadress"].strip()

    # Use purpose — prefer the human-readable text
    if isinstance(andmed.get("kaosIdTxt"), str) and andmed["kaosIdTxt"].strip():
        out["use_purpose"] = andmed["kaosIdTxt"].strip()

    # EHR code (validation/sanity — we already know the input)
    if isinstance(andmed.get("ehrKood"), str):
        out["ehr_code"] = andmed["ehrKood"].strip() or None

    # Kataster — first cadastral plot
    if isinstance(katastrid, list) and katastrid:
        first = katastrid[0]
        if isinstance(first, dict):
            kt = first.get("katastritunnus")
            if isinstance(kt, str) and kt.strip():
                out["kataster_no"] = kt.strip()

    # Geometry / dimensions
    if (v := _to_float(pohi.get("ehitisalunePind"))) is not None:
        out["footprint_m2"] = v
    if (v := _to_float(pohi.get("korgus"))) is not None:
        out["height_m"] = v
    if (v := _to_float(pohi.get("mahtBruto"))) is not None:
        out["volume_m3"] = v
    if (v := _to_int(pohi.get("maxKorrusteArv"))) is not None:
        out["storeys_above"] = v

    # Construction year — `kavKasutusKp` is "planned put-into-use date";
    # `ehAlustKp` is "construction-start date". Prefer kavKasutusKp
    # (closer to the legal completion year), fall back to ehAlustKp.
    year = (
        _year_from_iso(pohi.get("kavKasutusKp"))
        or _year_from_iso(pohi.get("ehAlustKp"))
    )
    # Also check the `kehand` array — sometimes it has esmane_kasutus.
    if year is None:
        kbody = kehand.get("kehand") if isinstance(kehand, dict) else None
        if isinstance(kbody, list) and kbody:
            for entry in kbody:
                if isinstance(entry, dict) and entry.get("esmane_kasutus"):
                    year = _to_int(entry["esmane_kasutus"])
                    if year:
                        break
    if year and 1700 < year < 2100:
        out["construction_year"] = year

    return out


__all__ = [
    "EhrSearchHit",
    "search_ehr",
    "lookup_ehr",
    "map_building_data",
]
