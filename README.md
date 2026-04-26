<div align="center">

<img src="assets/logo.svg" alt="TADF Ehitus OÜ" width="220"/>

# TADF Аудит

**Streamlit-based builder for Estonian _ehitise auditi aruanne_ (building-audit reports).**
Russian UI · Estonian output · §5 compliance gate · Claude-powered narrative & legal-ref helpers.

[![Deploy (Hetzner)](https://github.com/sapsan14/tadf-audit/actions/workflows/deploy-hetzner.yml/badge.svg)](https://github.com/sapsan14/tadf-audit/actions/workflows/deploy-hetzner.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![uv](https://img.shields.io/badge/managed%20by-uv-261230?logo=astral)](https://docs.astral.sh/uv/)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-FCC21B?logo=ruff)](https://docs.astral.sh/ruff/)
[![Tests](https://img.shields.io/badge/tests-22%20passing-brightgreen?logo=pytest&logoColor=white)](#tests)
[![Streamlit](https://img.shields.io/badge/built%20with-Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Powered by Claude](https://img.shields.io/badge/AI-Claude%204.6-D97706?logo=anthropic&logoColor=white)](https://www.anthropic.com)
[![Hosted on Hetzner](https://img.shields.io/badge/host-Hetzner-CC0000?logo=hetzner&logoColor=white)](https://www.hetzner.com)
[![Cloudflare DNS](https://img.shields.io/badge/DNS-Cloudflare-F38020?logo=cloudflare&logoColor=white)](https://www.cloudflare.com)
[![Docker](https://img.shields.io/badge/docker-multi--arch-2496ED?logo=docker&logoColor=white)](https://www.docker.com)
[![License](https://img.shields.io/badge/license-Proprietary-red)](#license)

**Live:** [tadf-audit.h2oatlas.ee](https://tadf-audit.h2oatlas.ee) · **Mirror:** [Streamlit Cloud](https://share.streamlit.io)

</div>

---

## Status

- **Phase 1 (Local MVP)** — shipped. Form + DOCX render + §5 legal checklist + SQLite + photos.
- **Phase 2 (LLM assist)** — shipped. Four helpers: narrative drafter, photo captioner, legal-ref ranker, Estonian polish.
- **Phase 5 (Hetzner deploy)** — shipped. Auto-provisioned ARM CAX11 + Caddy + Cloudflare DNS, ~€3.29/mo.

Coming next (in order):
- Restic backups + uptime monitoring
- Phase 4: PWA capture on the phone
- Phase 3: ASiC-E signing via Smart-ID (custom builder — `pyasice` is broken on Python 3.12+)
- Phase 6: EHR submission via X-tee (gated on RIA approval)

## Architecture in one paragraph

Streamlit UI (Russian) → Pydantic models → SQLAlchemy + SQLite persistence → docxtpl render against a per-subtype master template → final `.docx` download. Phase 2 LLM helpers (Sonnet 4.6 for prose drafting + polish, Haiku 4.5 for photo captions + legal-ref ranking) plug into the Findings + Photos pages with explicit accept/reject diffs. Sections 11 (Kokkuvõte) and 14 (Lõpphinnang) are hard-locked from any AI assistance — auditor-only by both legal convention and project policy. Auth via `streamlit-authenticator` (bcrypt-hashed passwords in `auth.yaml` / Streamlit secrets), gating every page including direct URL access.

## API keys & secrets

`ANTHROPIC_API_KEY` resolution order:

1. `ANTHROPIC_API_KEY` environment variable
2. `~/.anthropic/key` file (shared with other Anthropic tools)
3. `st.secrets["ANTHROPIC_API_KEY"]` (Streamlit Cloud)

Auth config (`auth.yaml`) is read from the repo root locally; on Streamlit Cloud it's pasted into Settings → Secrets as a multiline `auth_yaml = """…"""` value.

**Hard rules enforced in code:**
- Sections 11 / 14 — drafter and polish refuse to touch them.
- The ranker picks from `legal/references.yaml`; it cannot invent citations.
- Every LLM output is shown as a diff and explicitly accepted before render.
- 7-year retention on every artifact under `data/audits/<id>/`.
- Read-only access to `/audit/`; the source corpus is never modified.

## Install (local laptop)

Prerequisites: Python 3.12+, [`uv`](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:sapsan14/tadf-audit.git
cd tadf-audit
uv sync                    # core deps
uv sync --group dev        # + ruff, pytest
uv sync --group corpus     # + pdfplumber, pytesseract (for historical ingestion)

# Run
uv run streamlit run app/main.py
```

Open <http://localhost:8501>. UI is in Russian (Fjodor's language) with Estonian terms preserved for the fields that appear in the report.

## Tests

```bash
uv run pytest      # 22 tests
uv run ruff check  # lint
```

## CLI scripts

```bash
# Parse the historical .docx corpus → data/corpus/*.json (reference data + few-shot pool).
uv run python scripts/ingest_corpus.py

# Rebuild the docxtpl master template after edits to build_master.py.
uv run python -m tadf.templates.build_master
```

## Data layout

```
data/
  audits/<id>/
    photos/        photo originals (sha256-named)
    draft.docx     rendered output
    context.json   exact render context (7-year retention)
  corpus/          JSON snapshots of historical reports (reference)
  cache/llm/       prompt-cache + Claude usage log (cost tracker)
tadf.db            SQLite database
```

## Typical session

1. **📝 Новый аудит** — seq_no / year / type / visit_date, both auditor blocks, client.
2. **🏠 Здание** — address, kataster_no / EHR code, dimensions, year, fire class.
3. **🔍 Находки** — observations per section. Sections 11 / 14 are auditor-only — required by the §5 checklist.
4. **📸 Фото** — upload photos, caption them (or have Claude do it), tag with `section_ref`.
5. **📄 Готовый отчёт** — verify §5 coverage → save to DB → render `draft.docx`.
6. **📚 Правовая база** — browse the curated reference table the AI ranker picks from.
7. Open `draft.docx` → final wording tweaks → export PDF → sign via DigiDoc → upload `.asice` to <https://ehitisregister.ee>.

## Deployment

- **Streamlit Community Cloud** — entry `app/main.py`, secrets pasted via Settings → Secrets.
- **Hetzner + Cloudflare** — see [`ops/README.md`](ops/README.md) for the full setup. CAX11 ARM, Caddy reverse proxy, automated GitHub Actions deploy.

## License

Proprietary — © 2026 TADF Ehitus OÜ & Anton Sokolov. All rights reserved. The codebase contains business logic for a registered Estonian construction-supervision practice; not licensed for redistribution.

For commercial inquiries, contact [sokolovmeister@gmail.com](mailto:sokolovmeister@gmail.com).
