"""Aimo Park adapter (stub).

Aimo Park (formerly Q-Park / Europark in NO) lists facilities at
https://aimopark.no/. They also expose live availability data via the
Aimo Park app backend. Implementation plan:

1. Start with the public facility listings (HTML) — name, address, city.
2. Investigate the mobile app traffic for a live-availability JSON endpoint.
3. Normalize to ``ParkingRecord``.

Implementation deferred — see TODO list in README.
"""

from __future__ import annotations

from ..models import ParkingRecord

SOURCE_TYPE = "aimopark"


def fetch() -> list[ParkingRecord]:
    raise NotImplementedError("Aimo Park adapter not yet implemented.")
