"""End-to-end tests for the FastAPI import endpoints."""

from __future__ import annotations

import os

# Same fixed secret as test_api_tokens so issued tokens validate.
os.environ["TADF_IMPORT_SECRET"] = "test-secret-do-not-deploy"

from fastapi.testclient import TestClient  # noqa: E402

from tadf.api.app import app  # noqa: E402
from tadf.api.tokens import issue  # noqa: E402

client = TestClient(app)


def test_health() -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "ts" in body


def test_userscript_served() -> None:
    r = client.get("/api/static/tadf-connector.user.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert "TADF Connector" in r.text


def test_import_ehr_no_auth_rejected() -> None:
    r = client.post("/api/import-ehr/1", json={"address": "Auga 8"})
    assert r.status_code == 401


def test_import_ehr_bad_token_rejected() -> None:
    r = client.post(
        "/api/import-ehr/1",
        json={"address": "Auga 8"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401


def test_import_ehr_audit_mismatch_forbidden() -> None:
    token = issue(99)
    r = client.post(
        "/api/import-ehr/1",
        json={"address": "Auga 8"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_import_ehr_happy_path() -> None:
    token = issue(1)
    r = client.post(
        "/api/import-ehr/1",
        json={"address": "Auga 8", "ehrCode": "102032773"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Source-URL": "https://livekluster.ehr.ee/ui/ehr/v1/buildings/102032773",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["audit_id"] == 1
    assert isinstance(body["id"], int)


def test_import_teatmik_happy_path() -> None:
    token = issue(2)
    r = client.post(
        "/api/import-teatmik/2",
        json={"name": "UNTWERP OÜ", "reg_code": "14332941", "address": "Tallinn"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text


def test_pending_imports_round_trip() -> None:
    """After POSTing, the row should be readable from the Streamlit side."""
    from tadf.api.imports import list_pending, mark_applied, mark_rejected

    # Use a fresh audit_id so we don't collide with other tests.
    audit_id = 12345
    token = issue(audit_id)
    r = client.post(
        f"/api/import-ehr/{audit_id}",
        json={"address": "RT test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    new_id = r.json()["id"]

    pending = list_pending(audit_id)
    assert any(p.id == new_id for p in pending)

    mark_applied(new_id)
    after_apply = list_pending(audit_id)
    assert not any(p.id == new_id for p in after_apply)

    # Reject path
    r2 = client.post(
        f"/api/import-ehr/{audit_id}",
        json={"address": "reject me"},
        headers={"Authorization": f"Bearer {token}"},
    )
    new_id2 = r2.json()["id"]
    mark_rejected(new_id2)
    assert not any(p.id == new_id2 for p in list_pending(audit_id))
