"""Local filesystem storage helpers (raw + normalized)."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import FIELDS, ParkingRecord


def project_root() -> Path:
    """Return the project root directory (the one that contains ``data/``).

    Walks up from this file looking for a ``data`` sibling. Falls back to
    the current working directory if not found (useful in tests).
    """
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "data").is_dir():
            return parent
    return Path.cwd()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save_raw(payload: bytes | str | dict | list, *, source: str, ext: str = "json") -> Path:
    """Persist a raw API payload to ``data/raw/<source>_<ts>.<ext>``.

    Returns the path written. ``payload`` may be bytes, str, or a JSON-
    serialisable object. ``source`` is a short slug like ``parkeringsregister``.
    """
    out_dir = project_root() / "data" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{source}_{_timestamp()}.{ext}"

    if isinstance(payload, (dict, list)):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    elif isinstance(payload, bytes):
        path.write_bytes(payload)
    else:
        path.write_text(str(payload), encoding="utf-8")

    return path


def write_normalized_csv(records: Iterable[ParkingRecord], *, source: str) -> Path:
    """Write records to ``data/normalized/<source>.csv`` (overwriting)."""
    out_dir = project_root() / "data" / "normalized"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{source}.csv"

    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(FIELDS))
        writer.writeheader()
        for rec in records:
            writer.writerow(rec.to_row())

    return path
