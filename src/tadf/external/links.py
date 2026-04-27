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
    Otherwise → search query.
    """
    q = (query or "").strip()
    if not q:
        return None
    if q.isdigit() and 7 <= len(q) <= 9:
        return f"https://www.teatmik.ee/et/personlegal/{q}"
    return f"https://www.teatmik.ee/et/search?query={quote(q)}"


__all__ = ["ehr_building_url", "teatmik_company_url"]
