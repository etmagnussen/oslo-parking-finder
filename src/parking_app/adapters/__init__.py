"""Source adapters.

Each adapter exposes:

* ``SOURCE_TYPE`` — a short string identifying the upstream source.
* ``fetch() -> list[ParkingRecord]`` — returns normalized records.

Adapters that are not yet implemented raise ``NotImplementedError`` and
are kept as scaffolding so the rest of the pipeline can iterate on a
stable interface.
"""
