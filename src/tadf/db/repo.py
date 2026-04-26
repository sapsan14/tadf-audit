"""Convert between ORM rows and Pydantic models. Also: simple CRUD helpers."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from tadf.db.orm import (
    AuditorRow,
    AuditRow,
    BuildingRow,
    ClientRow,
    FindingRow,
    PhotoRow,
)
from tadf.models import (
    Audit,
    Auditor,
    Building,
    Client,
    Finding,
    Photo,
)


def _auditor_to_row(a: Auditor) -> AuditorRow:
    return AuditorRow(**a.model_dump(exclude={"id"}))


def _building_to_row(b: Building) -> BuildingRow:
    return BuildingRow(**b.model_dump(exclude={"id"}))


def _client_to_row(c: Client) -> ClientRow:
    return ClientRow(**c.model_dump(exclude={"id"}))


def _finding_to_row(f: Finding) -> FindingRow:
    d = f.model_dump(exclude={"id", "audit_id", "legal_ref_codes", "photo_ids"})
    return FindingRow(
        **d,
        legal_ref_codes_json=json.dumps(f.legal_ref_codes),
        photo_ids_json=json.dumps(f.photo_ids),
    )


def _photo_to_row(p: Photo) -> PhotoRow:
    return PhotoRow(**p.model_dump(exclude={"id", "audit_id"}))


def _row_to_auditor(r: AuditorRow) -> Auditor:
    return Auditor(
        id=r.id,
        full_name=r.full_name,
        company=r.company,
        company_reg_nr=r.company_reg_nr,
        kutsetunnistus_no=r.kutsetunnistus_no,
        qualification=r.qualification,
        id_code=r.id_code,
        independence_declaration=r.independence_declaration,
        signature_image_path=r.signature_image_path,
    )


def _row_to_building(r: BuildingRow) -> Building:
    return Building(
        id=r.id,
        address=r.address,
        kataster_no=r.kataster_no,
        ehr_code=r.ehr_code,
        use_purpose=r.use_purpose,
        construction_year=r.construction_year,
        last_renovation_year=r.last_renovation_year,
        designer=r.designer,
        builder=r.builder,
        footprint_m2=r.footprint_m2,
        height_m=r.height_m,
        volume_m3=r.volume_m3,
        storeys_above=r.storeys_above,
        storeys_below=r.storeys_below,
        fire_class=r.fire_class,
        pre_2003=r.pre_2003,
        substitute_docs_note=r.substitute_docs_note,
        site_area_m2=r.site_area_m2,
    )


def _row_to_client(r: ClientRow | None) -> Client | None:
    if r is None:
        return None
    return Client(
        id=r.id,
        name=r.name,
        reg_code=r.reg_code,
        contact_email=r.contact_email,
        contact_phone=r.contact_phone,
        address=r.address,
    )


def _row_to_finding(r: FindingRow) -> Finding:
    return Finding(
        id=r.id,
        audit_id=r.audit_id,
        section_ref=r.section_ref,
        severity=r.severity,
        observation_raw=r.observation_raw,
        observation_polished=r.observation_polished,
        accepted_polished=r.accepted_polished,
        recommendation=r.recommendation,
        legal_ref_codes=r.legal_ref_codes,
        photo_ids=r.photo_ids,
        status=r.status,
    )


def _row_to_photo(r: PhotoRow) -> Photo:
    return Photo(
        id=r.id,
        audit_id=r.audit_id,
        path=r.path,
        taken_at=r.taken_at,
        gps_lat=r.gps_lat,
        gps_lon=r.gps_lon,
        sha256=r.sha256,
        caption_auditor=r.caption_auditor,
        caption_llm_draft=r.caption_llm_draft,
        section_ref=r.section_ref,
        accepted=r.accepted,
    )


def save_audit(s: Session, audit: Audit) -> int:
    composer = _auditor_to_row(audit.composer)
    reviewer = _auditor_to_row(audit.reviewer)
    building = _building_to_row(audit.building)
    client = _client_to_row(audit.client) if audit.client else None
    s.add_all([composer, reviewer, building])
    if client:
        s.add(client)
    s.flush()

    row = AuditRow(
        seq_no=audit.seq_no,
        year=audit.year,
        type=audit.type,
        subtype=audit.subtype,
        purpose=audit.purpose,
        scope=audit.scope,
        methodology_version=audit.methodology_version,
        visit_date=audit.visit_date,
        status=audit.status,
        composer_id=composer.id,
        reviewer_id=reviewer.id,
        building_id=building.id,
        client_id=client.id if client else None,
    )
    s.add(row)
    s.flush()

    for f in audit.findings:
        fr = _finding_to_row(f)
        fr.audit_id = row.id
        s.add(fr)
    for p in audit.photos:
        pr = _photo_to_row(p)
        pr.audit_id = row.id
        s.add(pr)
    s.flush()
    return row.id


def load_audit(s: Session, audit_id: int) -> Audit:
    row = s.get(AuditRow, audit_id)
    if row is None:
        raise ValueError(f"Audit {audit_id} not found")
    return Audit(
        id=row.id,
        seq_no=row.seq_no,
        year=row.year,
        type=row.type,
        subtype=row.subtype,
        purpose=row.purpose,
        scope=row.scope,
        methodology_version=row.methodology_version,
        visit_date=row.visit_date,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        composer=_row_to_auditor(row.composer),
        reviewer=_row_to_auditor(row.reviewer),
        building=_row_to_building(row.building),
        client=_row_to_client(row.client),
        findings=[_row_to_finding(f) for f in row.findings],
        photos=[_row_to_photo(p) for p in row.photos],
    )


def list_audits(s: Session) -> list[Audit]:
    rows = s.query(AuditRow).order_by(AuditRow.year.desc(), AuditRow.seq_no.desc()).all()
    return [load_audit(s, r.id) for r in rows]
