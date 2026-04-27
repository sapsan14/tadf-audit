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
    """Deep link to «Kiirpäring katastrist» (quick parcel lookup) on the
    official Maa- ja Ruumiamet portal, pre-filled with the katastritunnus.

    Format: `https://ky.kataster.ee/ky/<katastritunnus>` with literal `:`
    separators (NOT percent-encoded). This is the verbatim example given
    by Maa-amet: «Katastriüksuse kiirpäringu tulemust on võimalik jagada
    lingi kaudu, lisades aadressi lõppu katastriüksuse tunnuse. Näide
    kiirpäringu tulemusest — https://ky.kataster.ee/ky/79501:027:0011»
    (geoportaal.maaamet.ee/est/teenused/kiirparing-maakatastrist-p123.html).

    History — what we tried before:
      - `geoportaal.maaamet.ee/.../Kinnistu-otsing-p82.html?otsing=…`
        silently redirected and dropped the query string.
      - `xgis.maaamet.ee/xgis2/page/app/maainfo?KAT_TUNNUS=…&ALAJAOTUS=…`
        and friends loaded the SPA shell but never navigated to the parcel.
      - `kataster.ee/?nr=…` — the homepage just rendered the home view
        and ignored the query string entirely (Fjodor confirmed: «открывает
        главную»). The `?nr=` did NOT trigger the quick-lookup widget.
        `ky.kataster.ee/ky/<tunnus>` is the actual subdomain that hosts
        the «Kiirpäring» SPA and consumes the path segment as input.
    """
    k = (kataster_no or "").strip()
    if not k:
        return None
    # `safe=":"` preserves the literal colons that the path-segment
    # form requires; quote() still encodes anything else dodgy.
    return f"https://ky.kataster.ee/ky/{quote(k, safe=':')}"


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
