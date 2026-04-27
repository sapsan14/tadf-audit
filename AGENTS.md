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
- **Phase 1 (local MVP):** **shipped.** Form + DOCX render + §5 checklist + SQLite + photo embed.
- **Phase 2 (LLM assist):** **shipped.** All four helpers wired. Models: Sonnet 4.6 (drafter, polish), Haiku 4.5 (captioner, ranker). Key resolution: env var → `~/.anthropic/key` → Streamlit secrets.
- **Project-doc AI extractor (2026-04-27):** **shipped.** Upload DOCX/PDF on Здание page → Haiku 4.5 extracts Building fields → preview/diff with checkbox accept → pending-slot apply. Cache in `data/cache/extract/`. Code: `src/tadf/llm/extractor.py` + `src/tadf/intake/document_extract.py`.
- **EHR direct API (2026-04-27, REVISED):** **shipped end-to-end.** Father pointed out EHR's detail-search SPA works without login; recon found two unauthenticated public endpoints: `/api/geoinfo/v1/getgeoobjectsbyaddress` (search by address/code) and `/api/building/v3/buildingData?ehr_code=...` (full building data). Both work from Hetzner without Keycloak. Code: `src/tadf/external/ehr_client.py`. UX: enter EHR code → click «🔎 Подгрузить из EHR» → preview/diff with all fields populated. «🔄 Свежие из EHR» bypasses 30-day cache. No browser helper needed for EHR.
- **Teatmik in-browser bridge (2026-04-27):** **shipped.** Teatmik is Cloudflare-protected (CAPTCHA tied to user IP), so direct Hetzner scraping fails. Solution: bookmarklet + Tampermonkey userscript. After auditor solves CAPTCHA in their browser, the helper reads the company-detail DOM and POSTs to `/api/import-teatmik/{audit_id}` (FastAPI sidecar at port 8001 in same container, Caddy routes `/api/*` → :8001). Per-audit HMAC token (24h TTL) embeds in URL fragment via `&tadf=...&target=client|designer|builder`. Token survives search→detail navigation via origin-scoped localStorage. Pending imports table + `@st.fragment(run_every="5s")` auto-polling so new rows surface within 5 seconds without user interaction. Code: `src/tadf/api/`, `assets/userscripts/tadf-connector.user.js`, `app/pages/7_🔌_Подключения.py`.
- **Auto-save drafts (2026-04-27):** **shipped.** `app/_state.py::ensure_draft_saved(audit)` upserts the in-memory draft as soon as the auditor types anything meaningful (address, ehr_code, kataster, purpose, client name, etc.). No more "click Save Draft first" — token-based features (Teatmik link, EHR import) work on the very first interaction. Wired into Новый аудит and Здание pages right after the form-field render.
- **Training corpus + few-shot wiring (2026-04-27):** **shipped.** `corpus_audit` + `corpus_section` SQL tables (`src/tadf/db/orm.py`) hold reference audits as plain text/JSON — provider-agnostic, so swapping Claude for any other LLM later doesn't lose the data. Ingest entry point `src/tadf/corpus/store.py::ingest_directory` (idempotent by SHA-256, supports `.docx`/`.pdf`/`.asice`/`.doc`; `.doc` needs LibreOffice on PATH and degrades cleanly when missing). Few-shot retrieval `src/tadf/llm/fewshot.py::examples_for(section_ref, subtype=)` returns 1–2 corpus paragraphs filtered by section + subtype with a hard skip on locked sections 11/14. Wired into `drafter.draft_narrative`, `polish.polish_text`, `improve.improve_text`, and `app/_widgets.improve_button_for` via an optional `subtype=` parameter (no breaking changes for existing call sites). Streamlit page `app/pages/8_📚_Корпус.py` lists the corpus, drills into per-audit sections, and accepts file uploads into `data/uploads/corpus/` (the `/audit/` source folder remains read-only). Tests: `tests/test_corpus_store.py`, `tests/test_corpus_parse_doc.py`, `tests/test_fewshot.py`. Initial ingest of the 12-audit archive: 8 imported (1 docx + 4 pdf + 3 asice), 4 .doc files require LibreOffice; 80% of section refs match canonical TADF keys.
- **LLM corpus extractor + extended intake formats (2026-04-27):** **shipped.** New `corpus_clause` table holds LLM-distilled units (boilerplate / finding / summary) with a per-row reusability score, source `model`, and `schema_version` for future re-extraction. Entry point `src/tadf/llm/corpus_extractor.py::extract_clauses_for_audit(audit_id)` runs Haiku 4.5 over every non-locked section, idempotent by `(section_id, model, schema_version)`. Few-shot retrieval (`fewshot.examples_for`) now prefers distilled clauses with reusability ≥ 0.5 over raw section bodies, with raw bodies as fallback when the extractor hasn't run for a section. Корпус page exposes a per-audit «🤖 Дистиллировать» button that surfaces the resulting clauses inline under each section. Project-document intake (`src/tadf/intake/document_extract.py`) now accepts `.doc` (via headless LibreOffice) and `.asice` (unzip + route inner payload) in addition to `.docx`/`.pdf`; `LibreofficeMissing` surfaces a tailored UI error on the Здание page. Tests: `tests/test_corpus_extractor.py` (20 cases, LLM monkeypatched), expanded `tests/test_fewshot.py` (distilled-clause priority + reusability filter), `tests/test_intake_formats.py` (.doc + .asice routing).
- **Phase 3 (signing):** not started. Smart-ID first per father's choice.
- All later phases: documented in the plan.

## Open questions for Fjodor — RESOLVED 2026-04-26

1. **Signing method:** **Smart-ID** (priority for Phase 3 implementation).
2. **TADF legal form:** **OÜ** — eligible for X-tee membership, Phase 6 not blocked architecturally.
3. **Insurer position:** **OK** with AI-assisted drafting + auditor review (conditions: diff-then-accept + methodology disclosure).
4. **Most common subtype:** **erakorraline** — but ship all three (`erakorraline`, `kasutuseelne`, `korraline`).
5. **Storage preference (new):** **local + remote duplicated** — Phase 5 must support bidirectional sync, not just cloud migration.
