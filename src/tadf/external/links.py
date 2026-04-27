"""Deep-link builders for EHR.ee and Teatmik.ee.

Why links instead of a scraper?

- **EHR.ee** — `livekluster.ehr.ee` exposes its data API behind Keycloak
  OAuth. Public URLs (`www.ehr.ee/app/...`) all serve the same React SPA
  shell that loads via authed XHR. Building a Keycloak client here would
  require Fjodor to supply credentials, store refresh tokens, and we'd
  still rate-limit ourselves out for a single-user tool.
- **Teatmik.ee** — anti-bot CAPTCHA on the company-detail pages. Headless
  scraping returns "Palun kinnitage, et Te ei ole robot!" instead of HTML.

Until proper API access is set up (separate sprint, requires either
RIA approval for EHR or a Teatmik API key), the highest-leverage UX is
a deep link: click → page opens in a new tab → father copies the fields
manually. That's still better than today (he searches each registry by
hand from scratch).

When real API access lands, drop these helpers and replace with
`ehr_client.lookup_ehr()` / `teatmik_client.lookup_company()` modules.
"""

from __future__ import annotations

from urllib.parse import quote


def ehr_building_url(ehr_code: str | None = None, kataster: str | None = None) -> str | None:
    """Deep link to a building page on the public EHR portal.

    Prefers EHR-code; falls back to kataster search.
    """
    if ehr_code and ehr_code.strip():
        # The SPA's deep-link path that the avalik viewer routes to.
        return f"https://livekluster.ehr.ee/ui/ehr/v1/buildings/{quote(ehr_code.strip())}"
    if kataster and kataster.strip():
        return f"https://www.ehr.ee/app/objects?kataster={quote(kataster.strip())}"
    return None


def teatmik_company_url(query: str) -> str | None:
    """Deep link to a Teatmik search/detail page.

    Numeric input → direct personlegal page (registry code).
    Otherwise → search query (path-style: `/et/search/<query>`,
    NOT `?query=…`).
    """
    q = (query or "").strip()
    if not q:
        return None
    if q.isdigit() and 7 <= len(q) <= 9:
        return f"https://www.teatmik.ee/et/personlegal/{q}"
    return f"https://www.teatmik.ee/et/search/{quote(q)}"


def maaamet_kataster_url(kataster_no: str | None) -> str | None:
    """Deep link to the official cadastre portal `kataster.ee`,
    pre-filled with the katastritunnus.

    History:
      - Legacy `geoportaal.maaamet.ee/.../Kinnistu-otsing-p82.html?otsing=…`
        silently redirects and drops the query string.
      - `xgis.maaamet.ee/xgis2/page/app/maainfo?KAT_TUNNUS=…&ALAJAOTUS=…`
        and its variants (KU=, TUNNUS=, ?, #) all loaded the SPA shell but
        never actually navigated to the parcel — Fjodor confirmed this on
        the deployed app («открывает только главную»).
      - `kataster.ee/?nr=…` is the new official Maa- ja Ruumiamet (MaRu)
        cadastre portal that DOES accept a query-string lookup. The HTML
        propagates `?nr=` even into the EST/ENG language switcher links,
        which is the strong signal that it's the canonical pattern.
    """
    k = (kataster_no or "").strip()
    if not k:
        return None
    return f"https://kataster.ee/?nr={quote(k)}"


def maaamet_xgis_kataster_url(kataster_no: str | None) -> str | None:
    """Backup map view on xgis.maaamet.ee. Same parameters as
    `maaamet_kataster_url` had previously — kept as a secondary link
    in case the new kataster.ee portal is unreachable. Many Estonian
    construction tools still link xgis2 directly even though the SPA
    doesn't always honour query params.
    """
    k = (kataster_no or "").strip()
    if not k:
        return None
    return (
        "https://xgis.maaamet.ee/xgis2/page/app/maainfo"
        f"?ALAJAOTUS=KIRG_KATASTRIYKSUSED&KAT_TUNNUS={quote(k)}"
    )


__all__ = [
    "ehr_building_url",
    "maaamet_kataster_url",
    "maaamet_xgis_kataster_url",
    "teatmik_company_url",
]
