# TADF — Audit-Report Builder (Phase 1)

Local-first Streamlit app for assembling Estonian *ehitise auditi aruanne* reports.

See `AGENTS.md` for the full project context, hard rules, and stack rationale.
See `PLAN_DEV_RU.md` for the developer-facing plan (Russian).
See `PLAN_FATHER_RU.docx` for the non-technical summary for Fjodor.

## Status

- **Phase 1 (Local MVP)** — shipped. Form + DOCX render + §5 legal checklist + SQLite + photos.
- **Phase 2 (LLM assist)** — shipped. Four helpers: narrative drafter, photo captioner, legal-ref ranker, Estonian polish.

Coming next:
- Phase 3: ASiC-E signing via `pyasice` + Smart-ID/ID-card
- Phase 4: PWA capture on the phone
- Phase 5: Hetzner deployment
- Phase 6: EHR submission via X-tee

### Phase 2 — `ANTHROPIC_API_KEY` resolution

The LLM features are off by default and turn on automatically when an API key is found, in this order:

1. `ANTHROPIC_API_KEY` environment variable
2. `~/.anthropic/key` file (Fjodor's preferred slot — same key shared with other Anthropic tools)
3. `st.secrets["ANTHROPIC_API_KEY"]` (Streamlit Cloud)

Models: Sonnet 4.6 for drafter + polish, Haiku 4.5 for captioner + ranker. Prompt caching enabled on every call.

**Hard rules enforced in code:** sections 11 (Kokkuvõte) and 14 (Lõpphinnang) are auditor-only — drafter and polish refuse to touch them. The ranker only ever picks from `legal/references.yaml`; it cannot invent citations.

## Install (local laptop)

Prerequisites: Python 3.12+, `uv` (https://docs.astral.sh/uv/).

```bash
git clone <repo> tadf && cd tadf
uv sync                    # core deps
uv sync --group dev        # + ruff, pytest
uv sync --group corpus     # + pdfplumber, pytesseract (for legacy ingestion)
```

## Run

```bash
uv run streamlit run app/main.py
```

Then open the URL Streamlit prints (default <http://localhost:8501>).

UI is in Russian (Fjodor's language) with Estonian terms preserved for fields
that appear in the report.

## Tests

```bash
uv run pytest
```

## CLI scripts

```bash
# Parse the historical .docx corpus into data/corpus/*.json (reference data,
# few-shot pool for Phase 2 LLM drafters).
uv run python scripts/ingest_corpus.py

# Rebuild the docxtpl master template after edits to build_master.py.
uv run python -m tadf.templates.build_master
```

## Data layout

```
data/
  audits/<id>/
    photos/        — photo originals (sha256-named)
    draft.docx     — rendered output
    context.json   — exact render context (7-year retention)
  corpus/          — JSON snapshots of historical reports (reference)
tadf.db            — SQLite database (Audit, Auditor, Building, Finding, Photo, Client)
```

## How a typical session looks

1. **Новый аудит** — fill seq_no/year/type/subtype/visit_date, both auditor blocks, client.
2. **Здание** — address, kataster_no/EHR code, dimensions, year, fire class.
3. **Находки** — add observations per section. **Sections 11 (Kokkuvõte) and 14
   (Lõpphinnang) are auditor-only — required by the §5 checklist.**
4. **Фото** — upload photos, caption them, tag with `section_ref`.
5. **Готовый отчёт** — verify §5 coverage → save to DB → render `draft.docx`.
6. Open `draft.docx` in Word/LibreOffice → final wording tweaks → export PDF →
   sign via DigiDoc → upload `.asice` to <https://ehitisregister.ee>.

## Hard rules (do not break)

1. Sections 11 and 14 are auditor-only. No LLM drafting, no LLM polish.
2. The LLM (Phase 2) ranks legal references — never invents them.
3. Every LLM output is diffed and explicitly accepted before render.
4. Read-only access to `/audit/`. Never modify the source corpus.
5. 7-year retention on every artifact under `data/audits/<id>/`.
