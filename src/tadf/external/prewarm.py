"""Background cache warm-up for offline-first operation.

Walks every reg-code and every address ever entered into the audit
database, then refreshes their entries in the Ariregister + In-ADS
caches. After this runs once with network, the picker for those
entities works fully offline.

Designed to be safe to call repeatedly:
  - Cache hits in `lookup_company` / `search_address` short-circuit
    immediately, so a re-run within the TTL window costs ~ms per entity.
  - Network failures are swallowed with a warning so the worker never
    propagates an exception into Streamlit.

Two entry points:
  - `warm_all()` — synchronous, returns stats. Use from a button.
  - `warm_all_async()` — fire-and-forget daemon thread. Use at startup.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class PrewarmStats:
    companies_seen: int
    companies_warmed: int
    addresses_seen: int
    addresses_warmed: int


def collect_reg_codes() -> set[str]:
    """Distinct 8-digit reg-codes that ever lived in the audit DB.

    Pulls from both `client.reg_code` and `auditor.company_reg_nr`
    so the auditor's own company gets warmed too. Filters to the
    canonical 8-digit form — bad-shape codes are silently skipped
    so we don't make pointless network calls.
    """
    from tadf.db.orm import AuditorRow, ClientRow
    from tadf.db.session import session_scope

    out: set[str] = set()
    with session_scope() as s:
        for (val,) in s.query(ClientRow.reg_code).distinct():
            v = (val or "").strip()
            if v.isdigit() and len(v) == 8:
                out.add(v)
        for (val,) in s.query(AuditorRow.company_reg_nr).distinct():
            v = (val or "").strip()
            if v.isdigit() and len(v) == 8:
                out.add(v)
    return out


def collect_addresses() -> set[str]:
    """Distinct addresses from both buildings and clients."""
    from tadf.db.orm import BuildingRow, ClientRow
    from tadf.db.session import session_scope

    out: set[str] = set()
    with session_scope() as s:
        for (val,) in s.query(BuildingRow.address).distinct():
            v = (val or "").strip()
            if len(v) >= 4:
                out.add(v)
        for (val,) in s.query(ClientRow.address).distinct():
            v = (val or "").strip()
            if len(v) >= 4:
                out.add(v)
    return out


def warm_companies() -> tuple[int, int]:
    from tadf.external.ariregister_client import lookup_company

    codes = collect_reg_codes()
    warmed = 0
    for code in codes:
        try:
            if lookup_company(code) is not None:
                warmed += 1
        except Exception as e:  # noqa: BLE001
            log.warning("Prewarm failed for reg_code %s: %s", code, e)
    return len(codes), warmed


def warm_addresses() -> tuple[int, int]:
    from tadf.external.inaadress_client import search_address

    addrs = collect_addresses()
    warmed = 0
    for a in addrs:
        try:
            if search_address(a, limit=1):
                warmed += 1
        except Exception as e:  # noqa: BLE001
            log.warning("Prewarm failed for address %r: %s", a, e)
    return len(addrs), warmed


def warm_all() -> PrewarmStats:
    """Synchronous: walk DB → refresh Ariregister and In-ADS caches."""
    cs, cw = warm_companies()
    asn, aw = warm_addresses()
    stats = PrewarmStats(
        companies_seen=cs,
        companies_warmed=cw,
        addresses_seen=asn,
        addresses_warmed=aw,
    )
    log.info("Prewarm complete: %s", stats)
    return stats


def warm_all_async() -> threading.Thread:
    """Fire-and-forget daemon thread that runs `warm_all()`.

    Daemon=True so the worker can't hold up Streamlit shutdown.
    Returns the thread so callers can join() it in tests if needed.
    """
    t = threading.Thread(target=warm_all, name="tadf-prewarm", daemon=True)
    t.start()
    return t


__all__ = [
    "PrewarmStats",
    "collect_addresses",
    "collect_reg_codes",
    "warm_addresses",
    "warm_all",
    "warm_all_async",
    "warm_companies",
]
