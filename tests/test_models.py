"""Tests for the ParkingRecord data model and its CSV serialization.

Focus: the new Oslo kommune pricing/zone fields added 2026-05-22 must
round-trip through ``to_row()`` and stay backward-compatible (i.e. all
default to ``None`` so existing adapters do not break).
"""

from __future__ import annotations

from parking_app.models import FIELDS, ParkingRecord


# Field names introduced in the 2026-05-22 ADR "ParkingRecord-felter for
# Oslo kommune-data". Listed explicitly so the test fails if any field
# is renamed or dropped without an ADR update.
NEW_FIELDS = (
    "tariff_group",
    "price_per_hour_petrol",
    "price_per_hour_ev",
    "price_max_minutes",
    "price_active_hours",
    "residential_zone",
    "night_parking_forbidden",
    "total_spaces",
    "notes",
)


def test_new_fields_are_part_of_canonical_field_order() -> None:
    """All new fields must appear in FIELDS so the CSV writer includes them."""
    for name in NEW_FIELDS:
        assert name in FIELDS, f"missing field in FIELDS tuple: {name!r}"


def test_new_fields_default_to_none_for_backward_compat() -> None:
    """Existing adapters that don't set the new fields must keep working."""
    record = ParkingRecord(name="Test")
    for name in NEW_FIELDS:
        assert getattr(record, name) is None, (
            f"new field {name!r} must default to None for backward compatibility"
        )


def test_to_row_serializes_all_new_fields() -> None:
    """Constructing a record with every new field set yields the right CSV row."""
    record = ParkingRecord(
        name="Økern Torgvei mellom Spireaveien og enden",
        address="Økern Torgvei",
        municipality="OSLO",
        lat=59.936127,
        lon=10.80741,
        operator="Oslo kommune Bymiljøetaten",
        source_url="https://geodata.bymoslo.no/...",
        source_type="oslo_kommune_gateparkering",
        tariff_group="2310",
        price_per_hour_petrol=42.0,
        price_per_hour_ev=21.0,
        price_max_minutes=120,
        price_active_hours="man-fre 09-17",
        residential_zone="J",
        night_parking_forbidden=True,
        total_spaces=5,
        notes="Maks 2 timer",
    )

    row = record.to_row()

    # Every FIELDS key must be present (no drift between dataclass and tuple).
    assert set(row.keys()) == set(FIELDS)

    # The new fields must round-trip with the right values and types.
    assert row["tariff_group"] == "2310"
    assert row["price_per_hour_petrol"] == 42.0
    assert row["price_per_hour_ev"] == 21.0
    assert row["price_max_minutes"] == 120
    assert row["price_active_hours"] == "man-fre 09-17"
    assert row["residential_zone"] == "J"
    assert row["night_parking_forbidden"] is True
    assert row["total_spaces"] == 5
    assert row["notes"] == "Maks 2 timer"


def test_to_row_renders_unset_new_fields_as_empty_string() -> None:
    """Unset (None) fields render as '' in the CSV row, matching prior behavior."""
    record = ParkingRecord(name="Test")
    row = record.to_row()
    for name in NEW_FIELDS:
        assert row[name] == "", f"unset {name!r} should render as empty string, got {row[name]!r}"
