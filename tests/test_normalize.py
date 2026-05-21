"""Tests for the normalize logic in fetch_register.

These tests run offline against synthetic API responses.
"""

from __future__ import annotations

from parking_app.ingest.fetch_register import (
    SOURCE_TYPE,
    is_active,
    matches_municipality,
    normalize,
    normalize_many,
)


SAMPLE_ACTIVE_OSLO = {
    "id": 32771,
    "parkeringstilbyderNavn": "P-NORGE AS",
    "breddegrad": 59.920798,
    "lengdegrad": 10.750878,
    "deaktivert": None,
    "versjonsnummer": 2,
    "navn": "Maridalsveien 10",
    "adresse": "Maridalsveien 10",
    "postnummer": "0178",
    "poststed": "OSLO",
    "aktiveringstidspunkt": "2026-01-19T08:13:02Z",
}

SAMPLE_INACTIVE_OSLO = {
    **SAMPLE_ACTIVE_OSLO,
    "id": 98357,
    "deaktivert": {"deaktivertTidspunkt": "2025-04-12T13:36:41Z"},
    "navn": "Midlertidige vedtak",
}

SAMPLE_ACTIVE_BERGEN = {
    **SAMPLE_ACTIVE_OSLO,
    "id": 11111,
    "poststed": "BERGEN",
    "postnummer": "5003",
}


def test_is_active() -> None:
    assert is_active(SAMPLE_ACTIVE_OSLO)
    assert not is_active(SAMPLE_INACTIVE_OSLO)


def test_matches_municipality() -> None:
    assert matches_municipality(SAMPLE_ACTIVE_OSLO, "OSLO")
    assert matches_municipality(SAMPLE_ACTIVE_OSLO, "oslo")  # case-insensitive
    assert not matches_municipality(SAMPLE_ACTIVE_BERGEN, "OSLO")
    assert matches_municipality(SAMPLE_ACTIVE_BERGEN, None)  # no filter -> match all


def test_normalize_fields() -> None:
    rec = normalize(SAMPLE_ACTIVE_OSLO)
    assert rec.name == "Maridalsveien 10"
    assert rec.address == "Maridalsveien 10, 0178 OSLO"
    assert rec.municipality == "Oslo"
    assert rec.lat == 59.920798
    assert rec.lon == 10.750878
    assert rec.operator == "P-NORGE AS"
    assert rec.source_type == SOURCE_TYPE
    assert "32771" in (rec.source_url or "")
    assert rec.last_checked  # ISO timestamp


def test_normalize_many_filters_oslo_active() -> None:
    items = [SAMPLE_ACTIVE_OSLO, SAMPLE_INACTIVE_OSLO, SAMPLE_ACTIVE_BERGEN]
    out = normalize_many(items, municipality="OSLO", only_active=True)
    assert len(out) == 1
    assert out[0].name == "Maridalsveien 10"


def test_normalize_many_include_inactive() -> None:
    items = [SAMPLE_ACTIVE_OSLO, SAMPLE_INACTIVE_OSLO]
    out = normalize_many(items, municipality="OSLO", only_active=False)
    assert len(out) == 2
