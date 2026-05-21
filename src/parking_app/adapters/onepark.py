"""Onepark adapter (stub).

Onepark operates several parking facilities in Oslo. They do not currently
publish an open API. Plan for implementation:

1. Try to obtain a CSV/JSON feed from onepark.no contact.
2. If none is available, parse the public listings on
   https://www.onepark.no/ ("Finn parkering" pages) and extract:
       - facility name
       - address
       - city/municipality
       - price/price-per-hour where listed
       - lat/lon (geocode address via e.g. Kartverket if not exposed)

This module currently exposes only the interface so the rest of the
pipeline can depend on it.
"""

from __future__ import annotations

from ..models import ParkingRecord

SOURCE_TYPE = "onepark"


def fetch() -> list[ParkingRecord]:
    raise NotImplementedError("Onepark adapter not yet implemented.")
