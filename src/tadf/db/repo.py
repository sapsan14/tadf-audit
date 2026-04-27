"""Convert between ORM rows and Pydantic models. Also: simple CRUD helpers."""

from __future__ import annotations

import json

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from tadf.db.orm import (
    AuditorRow,
    AuditRow,
    AuditSnapshotRow,
    BuildingRow,
    ClientRow,
    DirectoryAuditorRow,
    DirectoryBuilderRow,
    DirectoryClientRow,
    DirectoryDesignerRow,
    DirectoryUsePurposeRow,
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


def _filled_field_count(a: Auditor) -> int:
    """How many of the meaningful sibling fields are populated. Used as a
    tie-breaker when composer and reviewer share `full_name`."""
    return sum(
        1
        for v in (
            _strip_or_none(a.kutsetunnistus_no),
            _strip_or_none(a.qualification),
            _strip_or_none(a.company),
            _strip_or_none(a.company_reg_nr),
            _strip_or_none(a.id_code),
        )
        if v is not None
    )


def _mirror_to_directory(s: Session, audit: Audit) -> None:
    """Mirror the named entities of `audit` into the directory tables.

    Called from save_audit and upsert_audit on every write. Each upsert is
    keyed by name so the same person/company/value reuses one directory
    row. Empty-named entities are ignored (we don't want a "" entry in
    the dropdown).

    Collision handling: when `composer.full_name == reviewer.full_name`
    (case-insensitive after trim), the directory has only one slot for
    this person — writing both rows back-to-back would have the second
    write silently overwrite the first. Pick the side with MORE
    populated sibling fields and mirror only that one (tie → reviewer,
    matching the prior behaviour). Combined with `_set_if_present` in
    the upsert helpers, this means data the auditor typed in either
    role is preserved instead of being wiped by an empty counterpart.
    """
    composer = audit.composer
    reviewer = audit.reviewer
    composer_name = _strip_or_none(composer.full_name)
    reviewer_name = _strip_or_none(reviewer.full_name)
    if (
        composer_name is not None
        and reviewer_name is not None
        and composer_name.casefold() == reviewer_name.casefold()
    ):
        # Same person on both sides — pick the more-populated one.
        if _filled_field_count(composer) > _filled_field_count(reviewer):
            upsert_directory_auditor(s, composer)
        else:
            upsert_directory_auditor(s, reviewer)
    else:
        upsert_directory_auditor(s, composer)
        upsert_directory_auditor(s, reviewer)

    if audit.client is not None:
        upsert_directory_client(s, audit.client)
    if audit.building is not None:
        if audit.building.use_purpose:
            upsert_directory_use_purpose(s, audit.building.use_purpose)
        if audit.building.designer:
            upsert_directory_designer(s, audit.building.designer)
        if audit.building.builder:
            upsert_directory_builder(s, audit.building.builder)


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
        header_override=audit.header_override,
        footer_override=audit.footer_override,
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
    _mirror_to_directory(s, audit)
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
        header_override=row.header_override,
        footer_override=row.footer_override,
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


def list_drafts(s: Session) -> list[Audit]:
    rows = (
        s.query(AuditRow)
        .filter(AuditRow.status == "draft")
        .order_by(AuditRow.updated_at.desc(), AuditRow.id.desc())
        .all()
    )
    return [load_audit(s, r.id) for r in rows]


def _apply_auditor(row: AuditorRow, src: Auditor) -> None:
    row.full_name = src.full_name
    row.company = src.company
    row.company_reg_nr = src.company_reg_nr
    row.kutsetunnistus_no = src.kutsetunnistus_no
    row.qualification = src.qualification
    row.id_code = src.id_code
    row.independence_declaration = src.independence_declaration
    row.signature_image_path = src.signature_image_path


def _apply_building(row: BuildingRow, src: Building) -> None:
    row.address = src.address
    row.kataster_no = src.kataster_no
    row.ehr_code = src.ehr_code
    row.use_purpose = src.use_purpose
    row.construction_year = src.construction_year
    row.last_renovation_year = src.last_renovation_year
    row.designer = src.designer
    row.builder = src.builder
    row.footprint_m2 = src.footprint_m2
    row.height_m = src.height_m
    row.volume_m3 = src.volume_m3
    row.storeys_above = src.storeys_above
    row.storeys_below = src.storeys_below
    row.fire_class = src.fire_class
    row.pre_2003 = src.pre_2003
    row.substitute_docs_note = src.substitute_docs_note
    row.site_area_m2 = src.site_area_m2


def _apply_client(row: ClientRow, src: Client) -> None:
    row.name = src.name
    row.reg_code = src.reg_code
    row.contact_email = src.contact_email
    row.contact_phone = src.contact_phone
    row.address = src.address


def upsert_audit(s: Session, audit: Audit) -> int:
    """Insert if `audit.id is None`, otherwise update the existing row in place.

    Idempotent: repeated calls keep the same audit_id and never create
    duplicate Auditor/Building/Client rows. Findings and photos are rewritten
    wholesale on each update — `cascade='all, delete-orphan'` on the
    relationships handles the orphan cleanup.
    """
    if audit.id is None:
        new_id = save_audit(s, audit)
        audit.id = new_id
        return new_id

    row = s.get(AuditRow, audit.id)
    if row is None:
        # Stale id (e.g. user deleted the draft elsewhere) — fall back to insert.
        audit.id = None
        return save_audit(s, audit)

    _apply_auditor(row.composer, audit.composer)
    _apply_auditor(row.reviewer, audit.reviewer)
    _apply_building(row.building, audit.building)
    if audit.client is not None:
        if row.client is not None:
            _apply_client(row.client, audit.client)
        else:
            client_row = _client_to_row(audit.client)
            s.add(client_row)
            s.flush()
            row.client_id = client_row.id

    row.seq_no = audit.seq_no
    row.year = audit.year
    row.type = audit.type
    row.subtype = audit.subtype
    row.purpose = audit.purpose
    row.scope = audit.scope
    row.methodology_version = audit.methodology_version
    row.visit_date = audit.visit_date
    row.status = audit.status
    row.header_override = audit.header_override
    row.footer_override = audit.footer_override

    row.findings.clear()
    s.flush()
    for f in audit.findings:
        fr = _finding_to_row(f)
        fr.audit_id = row.id
        row.findings.append(fr)

    row.photos.clear()
    s.flush()
    for p in audit.photos:
        pr = _photo_to_row(p)
        pr.audit_id = row.id
        row.photos.append(pr)

    s.flush()
    _mirror_to_directory(s, audit)
    return row.id


# ---------------------------------------------------------------------------
# Directory upsert / delete helpers — called by `_mirror_to_directory` on
# every save and exposed for the «🗂 Справочник» management UI.
# ---------------------------------------------------------------------------


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _set_if_present(row, attr: str, value) -> None:
    """Update `row.<attr>` only when `value` is non-None.

    Audit forms have many fields that the auditor may legitimately leave
    empty (kutsetunnistus on a junior composer; reg_code on a private-
    person client; …). Without this guard, mirroring an audit save with
    a blanked field would WIPE OUT the directory entry's previously-
    populated value — losing data the auditor explicitly typed in earlier
    audits or in the «🗂 Справочник» edit form. Accumulate via repeated
    saves; the explicit cleanup channel is the «🗂 Справочник» row's
    edit form (which uses `update_directory_*` and DOES allow setting
    a field back to None).
    """
    cleaned = _strip_or_none(value) if isinstance(value, str) else value
    if cleaned is None:
        return
    setattr(row, attr, cleaned)


def upsert_directory_auditor(s: Session, src: Auditor) -> None:
    name = _strip_or_none(src.full_name)
    if name is None:
        return
    row = s.query(DirectoryAuditorRow).filter_by(full_name=name).one_or_none()
    if row is None:
        row = DirectoryAuditorRow(full_name=name)
        s.add(row)
    _set_if_present(row, "company", src.company)
    _set_if_present(row, "company_reg_nr", src.company_reg_nr)
    _set_if_present(row, "kutsetunnistus_no", src.kutsetunnistus_no)
    _set_if_present(row, "qualification", src.qualification)
    _set_if_present(row, "id_code", src.id_code)
    _set_if_present(row, "independence_declaration", src.independence_declaration)
    _set_if_present(row, "signature_image_path", src.signature_image_path)
    s.flush()


def upsert_directory_client(s: Session, src: Client) -> None:
    name = _strip_or_none(src.name)
    if name is None:
        return
    row = s.query(DirectoryClientRow).filter_by(name=name).one_or_none()
    if row is None:
        row = DirectoryClientRow(name=name)
        s.add(row)
    _set_if_present(row, "reg_code", src.reg_code)
    _set_if_present(row, "contact_email", src.contact_email)
    _set_if_present(row, "contact_phone", src.contact_phone)
    _set_if_present(row, "address", src.address)
    s.flush()


def _upsert_simple(s: Session, model, key_attr: str, value: str | None) -> None:
    cleaned = _strip_or_none(value)
    if cleaned is None:
        return
    row = s.query(model).filter(getattr(model, key_attr) == cleaned).one_or_none()
    if row is None:
        s.add(model(**{key_attr: cleaned}))
        s.flush()
    else:
        # Touch updated_at so the most-recently-used surfaces first in lists.
        row.updated_at = func.now()
        s.flush()


def upsert_directory_designer(s: Session, name: str | None) -> None:
    _upsert_simple(s, DirectoryDesignerRow, "name", name)


def upsert_directory_builder(s: Session, name: str | None) -> None:
    _upsert_simple(s, DirectoryBuilderRow, "name", name)


def upsert_directory_use_purpose(s: Session, value: str | None) -> None:
    _upsert_simple(s, DirectoryUsePurposeRow, "value", value)


def delete_directory_auditor(s: Session, full_name: str) -> bool:
    row = s.query(DirectoryAuditorRow).filter_by(full_name=full_name.strip()).one_or_none()
    if row is None:
        return False
    s.delete(row)
    s.flush()
    return True


def delete_directory_client(s: Session, name: str) -> bool:
    row = s.query(DirectoryClientRow).filter_by(name=name.strip()).one_or_none()
    if row is None:
        return False
    s.delete(row)
    s.flush()
    return True


def delete_directory_designer(s: Session, name: str) -> bool:
    row = s.query(DirectoryDesignerRow).filter_by(name=name.strip()).one_or_none()
    if row is None:
        return False
    s.delete(row)
    s.flush()
    return True


def delete_directory_builder(s: Session, name: str) -> bool:
    row = s.query(DirectoryBuilderRow).filter_by(name=name.strip()).one_or_none()
    if row is None:
        return False
    s.delete(row)
    s.flush()
    return True


def delete_directory_use_purpose(s: Session, value: str) -> bool:
    row = s.query(DirectoryUsePurposeRow).filter_by(value=value.strip()).one_or_none()
    if row is None:
        return False
    s.delete(row)
    s.flush()
    return True


def list_directory_auditors(s: Session) -> list[DirectoryAuditorRow]:
    return list(
        s.query(DirectoryAuditorRow).order_by(DirectoryAuditorRow.full_name).all()
    )


def list_directory_clients(s: Session) -> list[DirectoryClientRow]:
    return list(s.query(DirectoryClientRow).order_by(DirectoryClientRow.name).all())


def list_directory_designers(s: Session) -> list[DirectoryDesignerRow]:
    return list(s.query(DirectoryDesignerRow).order_by(DirectoryDesignerRow.name).all())


def list_directory_builders(s: Session) -> list[DirectoryBuilderRow]:
    return list(s.query(DirectoryBuilderRow).order_by(DirectoryBuilderRow.name).all())


def list_directory_use_purposes(s: Session) -> list[DirectoryUsePurposeRow]:
    return list(
        s.query(DirectoryUsePurposeRow).order_by(DirectoryUsePurposeRow.value).all()
    )


def update_directory_auditor(
    s: Session,
    *,
    row_id: int,
    full_name: str,
    company: str | None = None,
    company_reg_nr: str | None = None,
    kutsetunnistus_no: str | None = None,
    qualification: str | None = None,
    id_code: str | None = None,
) -> bool:
    """Update an existing directory_auditor row in place. The Справочник
    edit form calls this when the auditor saves changes.

    Returns True on success, False if the row was deleted concurrently.
    Raises ValueError if `full_name` collides with another row's name
    (uniqueness is the table's invariant, and silent merging would
    confuse the auditor — better to surface the conflict)."""
    row = s.get(DirectoryAuditorRow, row_id)
    if row is None:
        return False
    new_name = (full_name or "").strip()
    if not new_name:
        raise ValueError("Имя не может быть пустым")
    if new_name != row.full_name:
        clash = (
            s.query(DirectoryAuditorRow)
            .filter(DirectoryAuditorRow.full_name == new_name)
            .filter(DirectoryAuditorRow.id != row_id)
            .one_or_none()
        )
        if clash is not None:
            raise ValueError(
                f"Имя «{new_name}» уже занято в справочнике (id={clash.id})"
            )
    row.full_name = new_name
    row.company = _strip_or_none(company)
    row.company_reg_nr = _strip_or_none(company_reg_nr)
    row.kutsetunnistus_no = _strip_or_none(kutsetunnistus_no)
    row.qualification = _strip_or_none(qualification)
    row.id_code = _strip_or_none(id_code)
    s.flush()
    return True


def update_directory_client(
    s: Session,
    *,
    row_id: int,
    name: str,
    reg_code: str | None = None,
    contact_email: str | None = None,
    contact_phone: str | None = None,
    address: str | None = None,
) -> bool:
    row = s.get(DirectoryClientRow, row_id)
    if row is None:
        return False
    new_name = (name or "").strip()
    if not new_name:
        raise ValueError("Имя не может быть пустым")
    if new_name != row.name:
        clash = (
            s.query(DirectoryClientRow)
            .filter(DirectoryClientRow.name == new_name)
            .filter(DirectoryClientRow.id != row_id)
            .one_or_none()
        )
        if clash is not None:
            raise ValueError(
                f"Заказчик «{new_name}» уже есть в справочнике (id={clash.id})"
            )
    row.name = new_name
    row.reg_code = _strip_or_none(reg_code)
    row.contact_email = _strip_or_none(contact_email)
    row.contact_phone = _strip_or_none(contact_phone)
    row.address = _strip_or_none(address)
    s.flush()
    return True


def _update_simple(s: Session, model, key_attr: str, row_id: int, value: str) -> bool:
    row = s.get(model, row_id)
    if row is None:
        return False
    new_value = (value or "").strip()
    if not new_value:
        raise ValueError("Значение не может быть пустым")
    current = getattr(row, key_attr)
    if new_value != current:
        clash = (
            s.query(model)
            .filter(getattr(model, key_attr) == new_value)
            .filter(model.id != row_id)
            .one_or_none()
        )
        if clash is not None:
            raise ValueError(f"«{new_value}» уже есть в справочнике")
    setattr(row, key_attr, new_value)
    # Also bump updated_at so freshly-edited entries float to the top of
    # any "recently changed" UI in the future.
    row.updated_at = func.now()
    s.flush()
    return True


def update_directory_designer(s: Session, *, row_id: int, name: str, reg_code: str | None = None) -> bool:
    row = s.get(DirectoryDesignerRow, row_id)
    if row is None:
        return False
    new_name = (name or "").strip()
    if not new_name:
        raise ValueError("Название не может быть пустым")
    if new_name != row.name:
        clash = (
            s.query(DirectoryDesignerRow)
            .filter(DirectoryDesignerRow.name == new_name)
            .filter(DirectoryDesignerRow.id != row_id)
            .one_or_none()
        )
        if clash is not None:
            raise ValueError(f"«{new_name}» уже есть в справочнике")
    row.name = new_name
    row.reg_code = _strip_or_none(reg_code)
    s.flush()
    return True


def update_directory_builder(s: Session, *, row_id: int, name: str, reg_code: str | None = None) -> bool:
    row = s.get(DirectoryBuilderRow, row_id)
    if row is None:
        return False
    new_name = (name or "").strip()
    if not new_name:
        raise ValueError("Название не может быть пустым")
    if new_name != row.name:
        clash = (
            s.query(DirectoryBuilderRow)
            .filter(DirectoryBuilderRow.name == new_name)
            .filter(DirectoryBuilderRow.id != row_id)
            .one_or_none()
        )
        if clash is not None:
            raise ValueError(f"«{new_name}» уже есть в справочнике")
    row.name = new_name
    row.reg_code = _strip_or_none(reg_code)
    s.flush()
    return True


def update_directory_use_purpose(s: Session, *, row_id: int, value: str) -> bool:
    return _update_simple(s, DirectoryUsePurposeRow, "value", row_id, value)


def backfill_directory(s: Session) -> dict[str, int]:
    """One-time copy of existing AuditorRow / ClientRow / BuildingRow values
    into the directory tables. Idempotent: rows already present (keyed by
    name/value) are not duplicated, and existing directory rows are NOT
    overwritten by older audit data.

    Run from `init_db()` so the first deploy after this migration ships
    surfaces the auditor's accumulated history in the dropdowns immediately,
    instead of forcing them to re-pick every name once.
    """
    counts = {
        "auditor": 0,
        "client": 0,
        "designer": 0,
        "builder": 0,
        "use_purpose": 0,
    }

    # Auditors — for every distinct name, take the *latest* AuditorRow as the
    # canonical version (matches `latest_auditor_by_name`'s contract).
    seen_names: set[str] = {
        r.full_name for r in s.query(DirectoryAuditorRow.full_name).all() if r.full_name
    } if False else set(
        n for (n,) in s.query(DirectoryAuditorRow.full_name).all() if n
    )
    audit_rows = (
        s.query(AuditorRow).order_by(AuditorRow.id.desc()).all()
    )
    for ar in audit_rows:
        n = (ar.full_name or "").strip()
        if not n or n in seen_names:
            continue
        s.add(
            DirectoryAuditorRow(
                full_name=n,
                company=_strip_or_none(ar.company),
                company_reg_nr=_strip_or_none(ar.company_reg_nr),
                kutsetunnistus_no=_strip_or_none(ar.kutsetunnistus_no),
                qualification=_strip_or_none(ar.qualification),
                id_code=_strip_or_none(ar.id_code),
                independence_declaration=ar.independence_declaration,
                signature_image_path=ar.signature_image_path,
            )
        )
        seen_names.add(n)
        counts["auditor"] += 1

    # Clients
    seen_clients = {
        n for (n,) in s.query(DirectoryClientRow.name).all() if n
    }
    for cr in s.query(ClientRow).order_by(ClientRow.id.desc()).all():
        n = (cr.name or "").strip()
        if not n or n in seen_clients:
            continue
        s.add(
            DirectoryClientRow(
                name=n,
                reg_code=_strip_or_none(cr.reg_code),
                contact_email=_strip_or_none(cr.contact_email),
                contact_phone=_strip_or_none(cr.contact_phone),
                address=_strip_or_none(cr.address),
            )
        )
        seen_clients.add(n)
        counts["client"] += 1

    # Designers / Builders / Use_purpose — distinct strings from BuildingRow.
    for col, model, key, bucket in (
        (BuildingRow.designer, DirectoryDesignerRow, "name", "designer"),
        (BuildingRow.builder, DirectoryBuilderRow, "name", "builder"),
        (BuildingRow.use_purpose, DirectoryUsePurposeRow, "value", "use_purpose"),
    ):
        seen = {v for (v,) in s.query(getattr(model, key)).all() if v}
        distinct_values = {
            (v or "").strip() for (v,) in s.query(col).all() if v and v.strip()
        }
        for v in distinct_values - seen:
            s.add(model(**{key: v}))
            counts[bucket] += 1

    s.flush()
    return counts


def next_seq_no(s: Session, year: int) -> int:
    """Next auditor-facing audit number for the given year (1-based).

    Counts every row, including drafts, so two drafts created the same
    day cannot collide. If the year is empty, returns 1.
    """
    current = s.query(func.max(AuditRow.seq_no)).filter(AuditRow.year == year).scalar()
    return int(current or 0) + 1


def delete_audit(s: Session, audit_id: int) -> None:
    """Hard-delete an audit and its findings/photos (cascade).

    Auditor/Building/Client rows are intentionally preserved — they may be
    shared across audits, and the 7-year retention rule covers signed
    artifacts on disk, not the SQLite mirror.
    """
    row = s.get(AuditRow, audit_id)
    if row is None:
        return
    # AuditRow's cascade covers findings + photos; snapshots have their
    # own ondelete=CASCADE FK, but SQLite-on-Python often skips that
    # without `PRAGMA foreign_keys=ON`. Delete snapshots explicitly so
    # we don't leak orphans either way.
    s.execute(delete(AuditSnapshotRow).where(AuditSnapshotRow.audit_id == audit_id))
    s.delete(row)
    s.flush()


# ---------------------------------------------------------------------------
# Audit history (snapshots) — see tadf.db.orm.AuditSnapshotRow
# ---------------------------------------------------------------------------

# Maximum snapshots kept per audit. Older versions are dropped from the
# bottom on each new save. 30 ≈ a couple of weeks of "every meaningful
# edit" for an actively-edited draft.
SNAPSHOT_LIMIT = 30


def save_snapshot(s: Session, audit_id: int, snapshot_json: str) -> int:
    """Append a new snapshot for `audit_id`. Returns the new version_no.
    Caps the total at SNAPSHOT_LIMIT by deleting the oldest beyond that
    in the same transaction."""
    last_version = (
        s.execute(
            select(func.max(AuditSnapshotRow.version_no)).where(
                AuditSnapshotRow.audit_id == audit_id
            )
        ).scalar()
        or 0
    )
    new_version = last_version + 1
    s.add(
        AuditSnapshotRow(
            audit_id=audit_id,
            version_no=new_version,
            snapshot_json=snapshot_json,
        )
    )
    # Flush so the new row is visible to the cap query below; without
    # this, offset(LIMIT) only sees the pre-insert rows and the table
    # creeps up by one each call.
    s.flush()
    # Drop oldest beyond the limit.
    stale_ids = s.execute(
        select(AuditSnapshotRow.id)
        .where(AuditSnapshotRow.audit_id == audit_id)
        .order_by(AuditSnapshotRow.version_no.desc())
        .offset(SNAPSHOT_LIMIT)
    ).scalars().all()
    if stale_ids:
        s.execute(
            delete(AuditSnapshotRow).where(AuditSnapshotRow.id.in_(stale_ids))
        )
    s.flush()
    return new_version


def list_snapshots(s: Session, audit_id: int) -> list[AuditSnapshotRow]:
    """Newest-first list of all snapshots for an audit."""
    return list(
        s.execute(
            select(AuditSnapshotRow)
            .where(AuditSnapshotRow.audit_id == audit_id)
            .order_by(AuditSnapshotRow.version_no.desc())
        ).scalars()
    )


def load_snapshot(s: Session, snapshot_id: int) -> Audit | None:
    """Return the Audit Pydantic model from a snapshot row, or None if
    the row is missing or the JSON is malformed."""
    row = s.get(AuditSnapshotRow, snapshot_id)
    if row is None:
        return None
    try:
        return Audit.model_validate_json(row.snapshot_json)
    except Exception:
        return None
