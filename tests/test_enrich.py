"""Offline tests for fetch_register_details.enrich."""

from __future__ import annotations

from parking_app.ingest.fetch_register_details import (
    _to_bool_ja_nei,
    _to_int,
    enrich,
)


LIST_ITEM = {
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
}


DETAIL_PAYLOAD = {
    "id": 32771,
    "aktivVersjon": {
        "antallAvgiftsbelagtePlasser": 7,
        "antallAvgiftsfriePlasser": 3,
        "antallLadeplasser": 0,
        "antallForflytningshemmede": 1,
        "typeParkeringsomrade": "LANGS_KJOREBANE",
        "innfartsparkering": "NEI",
    },
}


def test_to_int() -> None:
    assert _to_int(7) == 7
    assert _to_int("7") == 7
    assert _to_int(None) is None
    assert _to_int("") is None
    assert _to_int("garbage") is None


def test_to_bool_ja_nei() -> None:
    assert _to_bool_ja_nei("JA") is True
    assert _to_bool_ja_nei("ja") is True
    assert _to_bool_ja_nei("NEI") is False
    assert _to_bool_ja_nei(None) is None
    assert _to_bool_ja_nei("kanskje") is None


def test_enrich_sets_all_capacity_fields() -> None:
    rec = enrich(LIST_ITEM, DETAIL_PAYLOAD)
    assert rec.name == "Maridalsveien 10"
    assert rec.paid_spaces == 7
    assert rec.free_spaces == 3
    assert rec.charging_spaces == 0
    assert rec.accessible_spaces == 1
    assert rec.facility_type == "LANGS_KJOREBANE"
    assert rec.is_park_and_ride is False


def test_enrich_missing_active_version_is_safe() -> None:
    rec = enrich(LIST_ITEM, {"id": 32771})  # no aktivVersjon
    assert rec.name == "Maridalsveien 10"
    assert rec.paid_spaces is None
    assert rec.free_spaces is None
    assert rec.is_park_and_ride is None


def test_enrich_park_and_ride_true() -> None:
    rec = enrich(
        LIST_ITEM,
        {"aktivVersjon": {"innfartsparkering": "JA", "antallAvgiftsfriePlasser": 50}},
    )
    assert rec.is_park_and_ride is True
    assert rec.free_spaces == 50
