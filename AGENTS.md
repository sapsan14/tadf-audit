# AGENTS.md — TADF audit-automation project

Notes for any Claude (or other agent) session that opens this repo. Read this first.

## What this project is

An automation toolkit for **TADF**, the one-person Estonian construction-supervision practice run by **Fjodor Sokolov** (kutsetunnistus 148515). TADF produces *ehitise auditi aruanne* (building-audit reports) — 16–60 page Estonian-language Word/PDF documents that today take 1–2 days each to assemble manually. The goal is to cut that to ~1 hour of structured intake + review + sign while staying compliant with Estonian law.

The owner of this repo (the user) is Fjodor's son — an experienced engineer, sole developer/operator. The actual end-user of the deployed system is Fjodor (Russian speaker, comfortable with Word but not with code).

## Who's involved

- **User (developer):** writes the code. Russian-speaking, technical. Wants Russian-language internal docs.
- **Fjodor (end user):** the auditor who signs the reports. Russian speaker; reports themselves are in Estonian (legal language). Needs a non-technical UI and a non-technical project summary in Russian.
- **Clients (downstream):** building owners, mostly in Ida-Virumaa (Narva, Narva-Jõesuu, Sillamäe based on corpus) — many Russian-speaking; reports go to **ehitisregister** (EHR) in Estonian.

## Source corpus

`/home/anton/projects/tadf/audit/` — 12 historical audit reports. Formats: `.docx`, legacy `.doc`, `.pdf`, `.asice` (Estonian signed-container ZIP). This is the eval corpus and few-shot pool. **Read-only.**

Filename convention (decoded from inspection):
`[seq][yy]_[type]_[license]_[object]_[label]_[date].ext`
- type: **EA** Ehitise Audit · **EP** Ehitusprojekti audit · **TJ** Tehniline järelevalve · **TP** Tehniline projekt · **AU** institutional audit
- license: **AA-1-01** / **AA-1-03** / **AR-3-01** = auditor qualification levels

## Key facts about the report

- ~60 % boilerplate, ~40 % variable. Templating + structured intake is the right shape.
- 16 standard sections (Tiitelleht → Sisukord → Üldosa → Auditi objekt → Kinnistu → Hoone ülevaatus → Arhitektuur → Tehnosüsteemid → Tulekaitse → Tehnilised näitajad → Kokkuvõte → Õiguslikud alused → Metoodika → Lõpphinnang → Allkirjad → Fotod).
- Sections **11 (Kokkuvõte)** and **14 (Lõpphinnang)** are the legally load-bearing assessments — **always auditor-only, no LLM drafting, no LLM polish.** Treat these as a hard rule.
- Reports are submitted to **ehitisregister.ee** (EHR) and signed as **ASiC-E**. 7-year retention is a legal requirement.

## Legal framework (the must-know acts)

Stored in `legal/references.yaml` once the project is scaffolded. Key acts:
- **Ehitusseadustik** (105032015001) — overall construction code
- **Ehitise auditi tegemise kord** (120102020004) — § 5 enumerates mandatory report fields (use this as the validation checklist)
- **Ehitise dokumendid ja juhendid** (118022020009) — hidden-works certificates, work diaries
- **Nõuded ehitusprojektile** (118072015007)
- **Korteriomandiseadus** (12742145) — apt ownership / energy certificates
- **Ehitise tehniliste andmete loetelu** (110062015008) — measurement standards
- **EhSRS** — Construction-Code Implementation Act; pre-2003 vs post-2003 substitute-documentation logic
- **Tuleohutuse seadus** (13314859) — fire-safety self-control
- **Ehitisregistrile esitamise kord** (12939670) — submission format

## Architecture in one paragraph

Streamlit UI (laptop, local-first) → SQLite + Pydantic models → docxtpl render against a per-subtype master template → `libreoffice --convert-to pdf` → `pyasice` ASiC-E signing (Phase 3) → manual EHR upload (Phase 1) or X-tee POST (Phase 6, gated on RIA approval). LLM (Claude Sonnet/Haiku) plugs in at Phase 2 for narrative drafting, photo captioning, legal-ref ranking, and Estonian polish — always diffed for accept/reject. Hetzner Docker deployment is Phase 5 (same code, swap SQLite→Postgres, disk→object storage).

## Stack (locked)

Python 3.12 · `uv` · `streamlit` · `sqlalchemy` 2 + `alembic` · `pydantic` v2 · `docxtpl` + `python-docx` · `libreoffice` (headless) · `pyasice` + `libdigidocpp` · `anthropic` SDK · `httpx` + `tenacity` · `pdfplumber` + `pytesseract` (est) · `ruff` · `pytest`. **Single Python codebase, no JS toolchain.**

## Project layout (target)

See `/home/anton/.claude/plans/look-into-audit-folder-playful-snail.md` for the full tree. Key directories:
- `app/` — Streamlit UI (`main.py` + `pages/`)
- `src/tadf/models/` — SQLAlchemy + Pydantic entities (Audit, Building, Auditor, Photo, Finding, LegalReference, TemplateClause)
- `src/tadf/templates/` — docxtpl masters per audit subtype + `boilerplate.yaml` + `partials/`
- `src/tadf/legal/` — `checklist.py` (§5 coverage), `references.yaml` (canonical citations)
- `src/tadf/render/` — context builder, docx render, pdf convert
- `src/tadf/llm/` — Phase 2: drafters, classifiers, polish
- `src/tadf/sign/` — Phase 3: asice + smartid + siva
- `src/tadf/external/` — EHR / Maa-amet / Kutsekoda clients
- `src/tadf/corpus/` — one-shot historical ingest
- `data/audits/<id>/` — per-audit artifacts (gitignored)
- `tests/` — snapshot + legal-checklist + corpus-parse tests

## User preferences captured during planning

- **Cloud target:** Hetzner (EU regions) — but **local laptop install first**.
- **MVP scope:** template + form only, no LLM, no signing. Document the full pipeline as later phases.
- **EHR submission:** stay manual until volume justifies X-tee.
- **LLM (Phase 2):** all four roles enabled — narrative drafting, photo captioning, legal-ref suggestion, Estonian polish.
- **Documentation language:** Russian for the developer plan **and** for the father-facing summary. Internal/code docs in English (this file).

## Hard rules (do not break)

1. **Sections 11 (Kokkuvõte) and 14 (Lõpphinnang) are auditor-only.** No LLM drafting, no LLM polish, no template-generated text. The auditor types these.
2. **Never invent legal citations.** LLM ranks from the curated `legal/references.yaml`; it does not generate references.
3. **Every LLM output renders as a diff** against auditor input with explicit accept/reject. Nothing reaches the rendered DOCX without a click.
4. **Never call EHR production** until RIA approval and dry-run testing complete. Use `vcrpy` against the test environment.
5. **7-year retention** is a legal floor — every artifact under `data/audits/<id>/` is preserved; deletion needs an explicit retention-lapsed flag.
6. **Estonian is the report language.** Russian/English are for UI and internal docs only.
7. **Read-only access to `/home/anton/projects/tadf/audit/`.** Never modify the source corpus.

## Where the planning artifacts live

- `/home/anton/.claude/plans/look-into-audit-folder-playful-snail.md` — full English plan (master document, most detail)
- `/home/anton/projects/tadf/PLAN_DEV_RU.md` — Russian translation for the developer
- `/home/anton/projects/tadf/PLAN_FATHER_RU.md` — short Russian summary (source for the DOCX)
- `/home/anton/projects/tadf/PLAN_FATHER_RU.docx` — DOCX version for Fjodor to mark up
- `/home/anton/projects/tadf/AGENTS.md` — this file

## Phase status

- **Phase 0 (planning):** done.
- **Phase 1 (local MVP):** not started. First action when implementation begins: scaffold `pyproject.toml`, ingest the 12-report corpus, build `ea_kasutuseelne.docx` master template.
- All later phases: documented in the plan.

## Open questions for Fjodor

These should be confirmed before Phase 3 work begins:
1. Signing method — ID-card / Mobile-ID / Smart-ID?
2. Is TADF an OÜ or FIE? (Affects X-tee eligibility for Phase 6.)
3. Does his professional-liability insurer accept LLM-assisted drafting with auditor review?
4. Which audit subtype is most common (drives which template ships in MVP — current guess: `ea_kasutuseelne`)?
