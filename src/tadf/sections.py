"""Canonical 14-section + subsection taxonomy for TADF audit reports.

Derived from:
  - The 12 historical reports under /audit/ (parsed via corpus ingester)
  - Estonian standards EVS 812-7 (fire safety), EVS 932 (project), and the
    structure mandated by Ehitise auditi tegemise kord §5
  - Subsections explicitly requested by Fjodor (e.g. "Pääs katusele ja
    korstnale", "Tehniliste süsteemide üldhinnang")

Findings get attached to a `section_ref` (e.g. "6.4", "8.8"). The §5 checklist
walks the canonical numbers (11, 14) to enforce auditor-only sections.
"""

from __future__ import annotations

# (key, label) — key is what gets stored in Finding.section_ref
SECTIONS: list[tuple[str, str]] = [
    # 4. Hoone ülevaatus
    ("4", "4. HOONE ÜLEVAATUS"),
    ("4.1", "4.1. Paikvaatluse läbiviimine"),
    ("4.2", "4.2. Ülevaatuse tulemus"),
    # 5. Arhitektuuri- ja ehituslik osa
    ("5", "5. HOONE ARHITEKTUURI- JA EHITUSLIK OSA"),
    ("5.1", "5.1. Arhitektuurne lahendus"),
    ("5.2", "5.2. Hoone üldkujundus"),
    ("5.3", "5.3. Krundi planeering ja juurdepääs"),
    # 6. Konstruktiivne osa
    ("6", "6. HOONE KONSTRUKTIIVNE OSA"),
    ("6.1", "6.1. Vundament"),
    ("6.2", "6.2. Välisseinad"),
    ("6.3", "6.3. Sisemüürid / vaheseinad"),
    ("6.4", "6.4. Vahelaed"),
    ("6.5", "6.5. Katuselagi / katus"),
    ("6.6", "6.6. Katusekate"),
    ("6.7", "6.7. Korsten"),
    ("6.8", "6.8. Viimistlus (välimine)"),
    ("6.9", "6.9. Viimistlus (sisemine)"),
    ("6.10", "6.10. Aknad"),
    ("6.11", "6.11. Välisuksed"),
    ("6.12", "6.12. Siseuksed"),
    ("6.13", "6.13. Vihmaveesüsteem"),
    ("6.14", "6.14. Trepid, rõdud ja varikatuste konstruktsioonid"),
    ("6.15", "6.15. Konstruktiivne üldhinnang"),
    # 7. Tehnosüsteemid
    ("7", "7. HOONE TEHNOSÜSTEEMID"),
    ("7.1", "7.1. Veevarustus"),
    ("7.2", "7.2. Kanalisatsioon"),
    ("7.3", "7.3. Elektrivarustus"),
    ("7.4", "7.4. Maandus ja piksekaitse"),
    ("7.5", "7.5. Küttesüsteemid (radiaator, ahi, kamin, soojuspump)"),
    ("7.6", "7.6. Ventilatsioon (loomulik / mehaaniline)"),
    ("7.7", "7.7. Sooja vee tootmine"),
    ("7.8", "7.8. Gaasivarustus"),
    ("7.9", "7.9. Sidetehnilised lahendused"),
    ("7.10", "7.10. Tehniliste süsteemide üldhinnang"),
    # 8. Tulekaitse / tuleohutus
    ("8", "8. HOONE TULEKAITSE OSA"),
    ("8.1", "8.1. Üldiseloomustus ja normid (EVS 812-7, Tuleohutuse seadus)"),
    ("8.2", "8.2. Tulepüsivusklass (TP-1 / TP-2 / TP-3)"),
    ("8.3", "8.3. Tuletundlikkus ja tarindite klassid (R, E, I)"),
    ("8.4", "8.4. Küttesüsteemid tuleohutuse seisukohalt"),
    ("8.5", "8.5. Tuletõkkesektsioonid"),
    ("8.6", "8.6. Evakuatsioon ja evakuatsiooniteed"),
    ("8.7", "8.7. Suitsueemaldus"),
    ("8.8", "8.8. Pääs katusele ja korstnale"),
    ("8.9", "8.9. Juurdepääs päästetöödeks"),
    ("8.10", "8.10. Välisveevarustus tulekustutuseks"),
    ("8.11", "8.11. Tulekustutid"),
    ("8.12", "8.12. Automaatne tulekahjusignalisatsioon (ATS)"),
    ("8.13", "8.13. Sprinklerid"),
    # 10. Tehnilised näitajad (per RT 110062015008)
    ("10", "10. HOONE TEHNILISED NÄITAJAD"),
    ("10.1", "10.1. Pindade jaotus"),
    ("10.2", "10.2. Kasutuspindade tabel"),
    ("10.3", "10.3. Ehitisregistri tehnilised andmed"),
    ("10.4", "10.4. Hoone maht ja gabariidid"),
    # 11. Kokkuvõte (auditor-only)
    ("11", "11. KOKKUVÕTE — только аудитор, без ИИ"),
    ("11.1", "11.1. Järeldused"),
    ("11.2", "11.2. Kasutusloa väljastamise alused"),
    # 13. Metoodika (mostly boilerplate)
    ("13", "13. AUDITI METOODIKA"),
    ("13.1", "13.1. Dokumendikontroll"),
    ("13.2", "13.2. Visuaalne ülevaatus"),
    ("13.3", "13.3. Tehniline analüüs"),
    ("13.4", "13.4. Järelduste koostamine"),
    # 14. Lõpphinnang (auditor-only)
    ("14", "14. AUDITI LÕPPHINNANG — только аудитор, без ИИ"),
    ("14.1", "14.1. Hinnang ehitises kasutatud tehniliste lahenduste kohta"),
    ("14.2", "14.2. Hinnang ehitise nõuetele vastavuse kohta"),
    ("14.3", "14.3. Kokkuvõtlik üldhinnang ehitisele"),
    # 16. Fotod
    ("16", "16. FOTOD"),
]

SECTION_KEYS = [k for k, _ in SECTIONS]
SECTION_LABELS = dict(SECTIONS)

# Top-level numbers used by render context (one finding-list slot per number)
TOP_LEVEL_NUMBERS = ["4", "5", "6", "7", "8", "10", "11", "13", "14", "16"]
