"""Oslo kommune / Bil i Oslo adapter (stub).

Oslo kommune publishes information about on-street parking, beboerparkering,
and a "Bil i Oslo" map at https://www.oslo.kommune.no/. Likely data sources:

* Open Data: https://data.oslo.kommune.no/ — search for "parkering".
* Bymiljøetaten dataset for street parking zones (often GeoJSON).
* Beboerparkering zones (GeoJSON via Geodata Norge / kommune).

Implementation plan:
1. Identify the most current dataset(s) on data.oslo.kommune.no.
2. Download GeoJSON / CSV.
3. Map polygon zones to representative point + zone name and normalize.

Implementation deferred — see TODO list in README.
"""

from __future__ import annotations

from ..models import ParkingRecord

SOURCE_TYPE = "oslo_kommune"


def fetch() -> list[ParkingRecord]:
    raise NotImplementedError("Oslo kommune adapter not yet implemented.")
