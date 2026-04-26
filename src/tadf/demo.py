"""Hand-crafted demo audits that load cleanly into a fresh DB.

Used as the seed when /audit/ isn't present (e.g. Streamlit Cloud) and as
optional sample data when a developer wipes the local DB. Designed to render
into a polished DOCX so the demo deploy looks credible.

Demo data is fictional — addresses are anonymised, EHR codes are placeholders.
"""

from __future__ import annotations

from datetime import date

from tadf.models import Audit, Auditor, Building, Client, Finding


def _fjodor() -> Auditor:
    return Auditor(
        full_name="Fjodor Sokolov",
        company="TADF Ehitus OÜ",
        company_reg_nr="12503172",
        kutsetunnistus_no="148515",
        qualification="Diplomeeritud insener tase 7",
    )


def demo_kasutuseelne() -> Audit:
    return Audit(
        seq_no=1,
        year=date.today().year,
        type="EA",
        subtype="kasutuseelne",
        purpose=(
            "Ehitise auditi koostamine on tingitud omaniku soovist seadustada ehitis ja "
            "saada kasutusluba. Auditi eesmärk on hinnata ehitise konstruktsioonide, "
            "tehnosüsteemide ja arhitektuurse lahenduse vastavust kehtivatele nõuetele "
            "ning hoone ohutust ja kasutamiskõlblikkust."
        ),
        scope=(
            "Hoone konstruktsioonid (vundament, seinad, vahelaed, katus), tehnosüsteemid "
            "(vesi, kanalisatsioon, elekter, küte, ventilatsioon) ja tuleohutus."
        ),
        visit_date=date(date.today().year, 6, 15),
        composer=_fjodor(),
        reviewer=_fjodor(),
        building=Building(
            address="Demo tn 1, Narva-Jõesuu linn, Ida-Viru maakond",
            kataster_no="51301:010:0001",
            ehr_code="100000001",
            use_purpose="aiamaja",
            construction_year=1985,
            footprint_m2=78.0,
            height_m=6.5,
            volume_m3=215.0,
            storeys_above=2,
            storeys_below=0,
            site_area_m2=650.0,
            fire_class="TP-3",
            designer="Tundmatu (algupärane projekt puudub)",
            builder="Tundmatu",
            pre_2003=True,
            substitute_docs_note=(
                "Algupärane ehitusprojekt puudub; käesolev audit asendab dokumentatsiooni "
                "EhSRS § 28 alusel."
            ),
        ),
        client=Client(
            name="Demo Klient OÜ",
            reg_code="12345678",
            contact_email="info@demo.example",
            contact_phone="+372 555 0001",
            address="Demo tn 1, Narva-Jõesuu",
        ),
        findings=[
            Finding(
                section_ref="4.1",
                severity="info",
                observation_raw=(
                    "Paikvaatlus toimus 15.06. visuaalkontrolli teel, tuginedes "
                    "esitatud ehitusdokumentidele ja kohapealsele mõõdistamisele."
                ),
            ),
            Finding(
                section_ref="6.1",
                severity="info",
                observation_raw=(
                    "Vundament on raudbetoonist lintvundament. Vundamendi seisund on "
                    "visuaalsel ülevaatusel hea — deformatsioone ega niiskuskahjustusi "
                    "ei tuvastatud."
                ),
            ),
            Finding(
                section_ref="6.2",
                severity="info",
                observation_raw=(
                    "Välisseinad on puidust palkkonstruktsioon. Konstruktsiooni "
                    "kandevõime on tagatud, deformatsioonid puuduvad."
                ),
            ),
            Finding(
                section_ref="6.5",
                severity="nonconf_minor",
                observation_raw=(
                    "Katus on puitkonstruktsioonil profiilplekk-katusega. Üksikud "
                    "kinnituskruvid on lahti tulnud — soovituslik kontroll järgmise "
                    "hooajaeelse hoolduse käigus."
                ),
                recommendation="Pinguta katuseplekk-katte kinnituskruvid 2 aasta jooksul.",
            ),
            Finding(
                section_ref="7.1",
                severity="info",
                observation_raw=(
                    "Veevarustus on lahendatud krundil asuva puurkaevu kaudu. "
                    "Veetorustik on PEX-toru, paigaldatud 2018. aastal."
                ),
            ),
            Finding(
                section_ref="7.3",
                severity="info",
                observation_raw=(
                    "Elektripaigaldus vastab EVS-HD 60364 nõuetele. Maandus ja "
                    "rikkevoolukaitse (RCD) on paigaldatud."
                ),
            ),
            Finding(
                section_ref="8.1",
                severity="info",
                observation_raw=(
                    "Hoone kuulub tulepüsivusklassi TP-3. Üksikelamutele kohaldatakse "
                    "Tuleohutuse seaduse ja EVS 812-7 nõudeid."
                ),
                legal_ref_codes=["Tuleohutuse seadus", "EVS 812-7"],
            ),
            Finding(
                section_ref="8.6",
                severity="info",
                observation_raw=(
                    "Evakuatsioon on lahendatud läbi peamise välisukse esikust. "
                    "Evakuatsioonitee pikkus jääb alla 25 m."
                ),
            ),
            Finding(
                section_ref="8.8",
                severity="info",
                observation_raw=(
                    "Pääs katusele on tagatud teisaldatava redeli abil. Korstnale "
                    "ligipääs katuselt on lahendatud katuseluugiga ja püsiastmetega."
                ),
            ),
            Finding(
                section_ref="11.1",
                severity="info",
                observation_raw=(
                    "Hoone on visuaalkontrolli põhjal heas seisukorras ja "
                    "kasutamiskõlblik. Tuvastatud üksikud puudused (katuseplekk) on "
                    "väikesed ega mõjuta hoone ohutust."
                ),
            ),
            Finding(
                section_ref="14.3",
                severity="info",
                observation_raw=(
                    "Lähtudes tehtud visuaalkontrollist, dokumentide analüüsist ja "
                    "Ehitusseadustiku nõuetest, vastab hoone oma ehitusaegsetele "
                    "nõuetele ja on ohutu kasutada. Soovitatav on katuse "
                    "kinnituste kontroll 2 aasta jooksul."
                ),
            ),
        ],
    )


def demo_erakorraline() -> Audit:
    return Audit(
        seq_no=2,
        year=date.today().year,
        type="EA",
        subtype="erakorraline",
        purpose=(
            "Erakorraline ehitise audit on tellitud omaniku poolt 2024. aasta "
            "tormikahjustuste hindamiseks ja hoone edasise kasutamiskõlblikkuse "
            "kindlaksmääramiseks."
        ),
        scope=(
            "Tormikahjustuste ulatuse hindamine — katus, korsten, välisseinte "
            "viimistlus ja drenaaž."
        ),
        visit_date=date(date.today().year, 4, 10),
        composer=_fjodor(),
        reviewer=_fjodor(),
        building=Building(
            address="Demo tee 7, Narva linn, Ida-Viru maakond",
            kataster_no="51101:020:0007",
            ehr_code="100000007",
            use_purpose="üksikelamu",
            construction_year=2008,
            footprint_m2=145.0,
            height_m=7.2,
            volume_m3=520.0,
            storeys_above=2,
            storeys_below=1,
            site_area_m2=1200.0,
            fire_class="TP-3",
        ),
        client=Client(name="Eraisik (anonüümne demo)"),
        findings=[
            Finding(
                section_ref="4.1",
                severity="info",
                observation_raw=(
                    "Paikvaatlus toimus 10.04. omaniku osavõtul. Visuaalselt "
                    "kontrolliti katust, korstnat ja välisseinte viimistlust."
                ),
            ),
            Finding(
                section_ref="6.6",
                severity="nonconf_major",
                observation_raw=(
                    "Katusekattes (savikivi) on tormi tagajärjel rebenenud "
                    "ligikaudu 12 m² ulatuses. Aluskatte-membraan on samuti "
                    "kahjustatud — vihmavesi tungib pööningule."
                ),
                recommendation=(
                    "Katusekatte vahetus 30 päeva jooksul. Vahepeal ajutine "
                    "katmine veekindla presendiga."
                ),
                legal_ref_codes=["EhS § 11"],
            ),
            Finding(
                section_ref="6.7",
                severity="hazard",
                observation_raw=(
                    "Korsten on tormi tagajärjel deformeerunud — tipupiirkonnas "
                    "on tellised lahti tulnud ja korsten kaldub umbes 5°. "
                    "Allakukkumisoht!"
                ),
                recommendation=(
                    "Korstna lammutamine ja taastamine pädeva ehitaja poolt "
                    "enne kütteperioodi algust. Senikaua kütmine keelatud."
                ),
                legal_ref_codes=["EhS § 11", "Tuleohutuse seadus"],
            ),
            Finding(
                section_ref="8.4",
                severity="hazard",
                observation_raw=(
                    "Korstna deformatsiooni tõttu on küttesüsteemi kasutamine "
                    "tuleohutuse seisukohalt KEELATUD kuni paranduseni."
                ),
                legal_ref_codes=["Tuleohutuse seadus"],
            ),
            Finding(
                section_ref="11.1",
                severity="nonconf_major",
                observation_raw=(
                    "Tormikahjustused on tõsised, kuid lokaliseeritud. Hoone "
                    "kandekonstruktsioonid (vundament, seinad, vahelaed) on "
                    "terved. Pärast katuse ja korstna remonti on hoone "
                    "kasutamiskõlblik."
                ),
            ),
            Finding(
                section_ref="14.1",
                severity="hazard",
                observation_raw=(
                    "Lõpphinnang: hoone vajab kiireloomulist katuse- ja "
                    "korstnaremonti. Kuni paranduseni on küttesüsteemi "
                    "kasutamine ja katuselähedaste ruumide kasutamine "
                    "ohutusjärelevalve all."
                ),
            ),
        ],
    )


def all_demos() -> list[Audit]:
    return [demo_kasutuseelne(), demo_erakorraline()]
