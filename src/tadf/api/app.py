"""FastAPI app — receives EHR / Teatmik payloads from the bookmarklet
or Tampermonkey userscript running in the auditor's browser.

Endpoints:
  GET  /api/health                        — uptime probe
  POST /api/import-ehr/{audit_id}         — body: arbitrary JSON from EHR
  POST /api/import-teatmik/{audit_id}     — body: arbitrary JSON from Teatmik

All POST endpoints require `Authorization: Bearer <token>` where the
token was issued by `tadf.api.tokens.issue()` for the same audit_id.

CORS: we whitelist livekluster.ehr.ee and www.teatmik.ee (the only
origins the helpers ever run from). Tokens add a second layer.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response

from tadf.api.tokens import verify
from tadf.db.orm import PendingImportRow
from tadf.db.session import init_db, session_scope

_USERSCRIPT_PATH = Path(__file__).resolve().parents[3] / "assets" / "userscripts" / "tadf-connector.user.js"

_ALLOWED_ORIGINS = [
    "https://livekluster.ehr.ee",
    "https://www.ehr.ee",
    "https://www.teatmik.ee",
    "https://teatmik.ee",
    # Browser bookmarklets execute in the page's origin; if the user is on
    # a non-https subpage of the same site, we still allow it.
    "https://ehr.ee",
]

app = FastAPI(
    title="TADF Import API",
    description=(
        "Receives EHR / Teatmik data from the in-browser helper "
        "(bookmarklet or Tampermonkey userscript). Auth: per-audit HMAC token."
    ),
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,  # tokens carry the auth — no cookies
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=3600,
)


# Make sure the schema exists when the API process starts (the Streamlit
# process also calls init_db, but they may start in either order).
init_db()


def _require_audit(authorization: str | None) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    audit_id = verify(token)
    if audit_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    return audit_id


def _record(audit_id: int, kind: str, payload: Any, source_url: str | None) -> int:
    """Persist a pending import. Returns the row id."""
    with session_scope() as s:
        row = PendingImportRow(
            audit_id=audit_id,
            kind=kind,
            payload_json=json.dumps(payload, ensure_ascii=False),
            source_url=source_url,
            received_at=datetime.utcnow(),
        )
        s.add(row)
        s.flush()
        return row.id


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "ts": datetime.utcnow().isoformat()}


@app.get("/api/static/tadf-connector.user.js")
def userscript() -> Response:
    """Serve the Tampermonkey userscript with the right Content-Type so
    Tampermonkey detects `.user.js` and offers to install on click."""
    if not _USERSCRIPT_PATH.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "userscript missing from build")
    return PlainTextResponse(
        _USERSCRIPT_PATH.read_text(encoding="utf-8"),
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/import-ehr/{path_audit_id}")
async def import_ehr(
    path_audit_id: int,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    audit_id = _require_audit(authorization)
    if audit_id != path_audit_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "token / path audit_id mismatch")
    payload = await request.json()
    source_url = request.headers.get("X-Source-URL")
    row_id = _record(audit_id, "ehr", payload, source_url)
    return {"ok": True, "id": row_id, "audit_id": audit_id}


@app.post("/api/import-teatmik/{path_audit_id}")
async def import_teatmik(
    path_audit_id: int,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    audit_id = _require_audit(authorization)
    if audit_id != path_audit_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "token / path audit_id mismatch")
    payload = await request.json()
    source_url = request.headers.get("X-Source-URL")
    row_id = _record(audit_id, "teatmik", payload, source_url)
    return {"ok": True, "id": row_id, "audit_id": audit_id}
