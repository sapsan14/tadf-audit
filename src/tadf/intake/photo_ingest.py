"""Extract EXIF metadata from a photo: date taken + GPS coordinates.

Used by the «📸 Фото» upload flow so we can:
  - sort the gallery by capture time (matches the order the auditor
    walked the site, regardless of upload order)
  - drop a future map pin on the building when GPS is present
  - cross-check the photo's date against the audit's `visit_date`

Falls back gracefully — any missing/malformed EXIF tag returns None
for that field rather than raising.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any


def _ratio(value: Any) -> float | None:
    """exifread returns ratios as `<num>/<den>`-style objects with .num/.den
    attrs (or as ints). Coerce to float."""
    try:
        if hasattr(value, "num") and hasattr(value, "den") and value.den:
            return float(value.num) / float(value.den)
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _dms_to_decimal(dms: list, ref: str | None) -> float | None:
    """Convert (degrees, minutes, seconds) tuple + N/S/E/W ref → decimal."""
    if not dms or len(dms) != 3:
        return None
    parts = [_ratio(p) for p in dms]
    if any(p is None for p in parts):
        return None
    deg, minutes, seconds = parts
    decimal = deg + minutes / 60.0 + seconds / 3600.0
    if ref in ("S", "W"):
        decimal = -decimal
    return decimal


def _parse_exif_datetime(s: str) -> datetime | None:
    """EXIF dates are 'YYYY:MM:DD HH:MM:SS' (note colons in the date)."""
    try:
        return datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def extract_exif(data: bytes) -> dict[str, Any]:
    """Return a small dict with {taken_at, gps_lat, gps_lon} parsed from
    the photo bytes. Missing keys mean the EXIF tag wasn't present /
    parseable — caller should treat absent values as `None`.

    Never raises: any error → empty dict (we don't want a malformed
    photo to block the upload flow).
    """
    try:
        import exifread
    except ImportError:
        return {}

    try:
        tags = exifread.process_file(BytesIO(data), details=False)
    except Exception:
        return {}

    out: dict[str, Any] = {}

    # Date taken — try several tags in order of reliability.
    for tag in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"):
        if tag in tags:
            dt = _parse_exif_datetime(str(tags[tag]))
            if dt:
                out["taken_at"] = dt
                break

    # GPS — both lat and lon need to be present (and their refs).
    gps_lat = tags.get("GPS GPSLatitude")
    gps_lat_ref = tags.get("GPS GPSLatitudeRef")
    gps_lon = tags.get("GPS GPSLongitude")
    gps_lon_ref = tags.get("GPS GPSLongitudeRef")
    if gps_lat and gps_lat_ref and gps_lon and gps_lon_ref:
        lat = _dms_to_decimal(list(gps_lat.values), str(gps_lat_ref))
        lon = _dms_to_decimal(list(gps_lon.values), str(gps_lon_ref))
        if lat is not None and lon is not None:
            out["gps_lat"] = lat
            out["gps_lon"] = lon

    return out


__all__ = ["extract_exif"]
