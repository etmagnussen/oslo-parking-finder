"""Shared data model for normalized parking records.

All adapters and ingest scripts should produce records that conform to
``ParkingRecord``. The CSV writer in ``parking_app.storage`` uses the
field order defined in ``FIELDS``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


# Canonical field order for normalized CSV output.
FIELDS: tuple[str, ...] = (
    "name",
    "address",
    "municipality",
    "lat",
    "lon",
    "operator",
    "source_url",
    "source_type",
    "last_checked",
)


@dataclass
class ParkingRecord:
    """A normalized parking facility record.

    Coordinates use WGS84 decimal degrees. ``last_checked`` is an ISO 8601
    UTC timestamp set automatically when a record is created.
    """

    name: str
    address: str | None = None
    municipality: str | None = None
    lat: float | None = None
    lon: float | None = None
    operator: str | None = None
    source_url: str | None = None
    source_type: str | None = None
    last_checked: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_row(self) -> dict[str, Any]:
        """Return a dict keyed by ``FIELDS`` suitable for ``csv.DictWriter``."""
        data = asdict(self)
        return {k: ("" if data.get(k) is None else data[k]) for k in FIELDS}
