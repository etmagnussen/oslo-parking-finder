"""Offline tests for the Oslo kommune (geodata.bymoslo.no) adapter.

No network. We feed synthetic GeoJSON Features that mirror the shape of
the real ArcGIS REST output and assert that ``normalize()`` produces the
expected ParkingRecord.
"""

from __future__ import annotations

from parking_app.adapters import oslo_kommune
from parking_app.adapters.oslo_kommune import (
    _centroid_of_first_ring,
    _parse_bool,
    _parse_duration_minutes,
    _parse_first_hour_price,
    _parse_int,
    _parse_number,
    _prop,
    normalize,
    normalize_many,
)


# ---------------------------------------------------------------------------
# Low-level parsers
# ---------------------------------------------------------------------------


def test_parse_number_handles_strings_and_numbers() -> None:
    assert _parse_number(42) == 42.0
    assert _parse_number(42.0) == 42.0
    assert _parse_number("42") == 42.0
    assert _parse_number("42 kr/time") == 42.0
    assert _parse_number("42,5 kr") == 42.5
    assert _parse_number("") is None
    assert _parse_number(None) is None
    assert _parse_number("ingen pris") is None


def test_parse_int_truncates() -> None:
    assert _parse_int("5") == 5
    assert _parse_int("5.9") == 5
    assert _parse_int(None) is None


def test_parse_duration_minutes_handles_hours_and_minutes() -> None:
    assert _parse_duration_minutes("2 timer") == 120
    assert _parse_duration_minutes("1 time") == 60
    assert _parse_duration_minutes("30 min") == 30
    assert _parse_duration_minutes("30") == 30  # bare number = minutes
    assert _parse_duration_minutes("1 t") == 60
    assert _parse_duration_minutes(None) is None
    assert _parse_duration_minutes("") is None
    # 'Ubegrenset' (unlimited) must NOT be conflated with 0 minutes.
    assert _parse_duration_minutes("Ubegrenset") is None
    assert _parse_duration_minutes("ingen begrensning") is None


def test_parse_first_hour_price_handles_tariff_table() -> None:
    # Real-world Bymiljøetaten format.
    s = "1 time 40 kr, 2 timer 81 kr, 3 timer 122 kr, 1 døgn 204 kr"
    assert _parse_first_hour_price(s) == 40.0
    s_ev = "1 time 20 kr, 2 timer 41 kr, 3 timer 61 kr"
    assert _parse_first_hour_price(s_ev) == 20.0
    # Decimal hour price.
    assert _parse_first_hour_price("1 time 19,5 kr, 2 timer 39 kr") == 19.5
    # Fallback: plain numeric string (used by tests and other layers).
    assert _parse_first_hour_price(42) == 42.0
    assert _parse_first_hour_price("42") == 42.0
    assert _parse_first_hour_price("42 kr/time") == 42.0
    # Empty / unparseable.
    assert _parse_first_hour_price(None) is None
    assert _parse_first_hour_price("") is None
    assert _parse_first_hour_price("ingen pris") is None


def test_prop_lookup_matches_qualified_and_bare_names() -> None:
    props = {
        "str.gisowner.STR_Parkering.beregnet_antall": 5,
        "navn": "Test",
    }
    assert _prop(props, "beregnet_antall") == 5  # via suffix match
    assert _prop(props, "navn") == "Test"        # via exact match
    assert _prop(props, "missing") is None


def test_parse_bool_handles_norwegian_and_english() -> None:
    assert _parse_bool("Ja") is True
    assert _parse_bool("NEI") is False
    assert _parse_bool(True) is True
    assert _parse_bool(False) is False
    assert _parse_bool(None) is None
    assert _parse_bool("kanskje") is None


def test_centroid_of_polygon_is_average_of_first_ring() -> None:
    # Square: (0,0)-(2,0)-(2,2)-(0,2)-(0,0). Centroid by averaging vertices
    # (including the closing duplicate) is (4/5, 4/5).
    geom = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
    }
    lon, lat = _centroid_of_first_ring(geom)
    assert lon is not None and lat is not None
    assert abs(lon - 0.8) < 1e-9
    assert abs(lat - 0.8) < 1e-9


def test_centroid_of_point_returns_point() -> None:
    geom = {"type": "Point", "coordinates": [10.7, 59.9]}
    assert _centroid_of_first_ring(geom) == (10.7, 59.9)


def test_centroid_of_missing_or_unknown_returns_none() -> None:
    assert _centroid_of_first_ring(None) == (None, None)
    assert _centroid_of_first_ring({"type": "LineString", "coordinates": [[0, 0], [1, 1]]}) == (None, None)


# ---------------------------------------------------------------------------
# Normalization end-to-end
# ---------------------------------------------------------------------------


def _økern_torgvei_feature() -> dict:
    """A realistic synthetic Feature mirroring Bymiljøetaten's schema.

    Uses the real fully-qualified property names from
    ``geodata.bymoslo.no/.../Parkering/MapServer/27`` to ensure the
    suffix-based lookup actually works against production data.
    """
    P = "str.gisowner.STR_Parkering."
    Q = "samferdsel.gisowner.parkering_pris."
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [10.80740, 59.93612],
                    [10.80750, 59.93612],
                    [10.80750, 59.93620],
                    [10.80740, 59.93620],
                    [10.80740, 59.93612],
                ]
            ],
        },
        "properties": {
            P + "objectid": 1234,
            P + "takstgruppe1": 2310,
            Q + "pris_bensin_diesel_hybrid": (
                "1 time 40 kr, 2 timer 81 kr, 3 timer 122 kr, "
                "4 timer 163 kr, 1 døgn 204 kr"
            ),
            Q + "pris_elbil": "1 time 20 kr, 2 timer 41 kr, 3 timer 61 kr",
            Q + "pris_maks_tid": "2 timer",
            Q + "pris_tidspunkt_du_må_betale": "Kl. 09:00-20:00 (man-lør)",
            P + "beboerparkeringssone": "J",
            P + "nattparkeringsforbud": "Nei",
            P + "beregnet_antall": 5,
            P + "befart_antall": 6,
            P + "fritekst": "Maks 2 timer for ikke-beboere",
        },
    }


def test_normalize_populates_all_pricing_fields() -> None:
    rec = normalize(_økern_torgvei_feature())
    assert rec is not None
    # Layer 27 has no street-name field — we synthesize one from zone + id.
    assert rec.name == "Gateparkering sone J #1234"
    assert rec.municipality == "Oslo"
    assert rec.operator == "Oslo kommune Bymiljøetaten"
    assert rec.source_type == oslo_kommune.SOURCE_TYPE
    assert rec.source_url.endswith("/1234")

    # Coordinates lie inside the Oslo bbox.
    assert rec.lat is not None and 59.81 <= rec.lat <= 60.13
    assert rec.lon is not None and 10.49 <= rec.lon <= 10.95

    # Pricing fields parsed correctly.
    assert rec.tariff_group == "2310"
    assert rec.price_per_hour_petrol == 40.0  # first-hour price from tariff table
    assert rec.price_per_hour_ev == 20.0
    assert rec.price_max_minutes == 120
    assert rec.price_active_hours == "Kl. 09:00-20:00 (man-lør)"
    assert rec.residential_zone == "J"
    assert rec.night_parking_forbidden is False
    assert rec.total_spaces == 5  # prefer beregnet_antall over befart_antall
    assert rec.notes == "Maks 2 timer for ikke-beboere"


def test_normalize_skips_feature_without_geometry() -> None:
    feat = _økern_torgvei_feature()
    feat["geometry"] = None
    assert normalize(feat) is None


def test_normalize_falls_back_to_befart_antall_when_beregnet_missing() -> None:
    feat = _økern_torgvei_feature()
    P = "str.gisowner.STR_Parkering."
    feat["properties"][P + "beregnet_antall"] = None
    feat["properties"][P + "befart_antall"] = 7
    rec = normalize(feat)
    assert rec is not None and rec.total_spaces == 7


def test_normalize_many_drops_features_without_coords() -> None:
    good = _økern_torgvei_feature()
    bad = _økern_torgvei_feature()
    bad["geometry"] = None
    out = normalize_many([good, bad, good])
    assert len(out) == 2


def test_normalize_handles_missing_pricing_gracefully() -> None:
    """A polygon with no pricing should still yield a record with Nones."""
    feat = _økern_torgvei_feature()
    feat["properties"] = {
        "OBJECTID": 99,
        "navn": "Test gate 1",
        "beregnet_antall": 3,
    }
    rec = normalize(feat)
    assert rec is not None
    # When the source provides an explicit name, we honor it.
    assert rec.name == "Test gate 1"
    assert rec.tariff_group is None
    assert rec.price_per_hour_petrol is None
    assert rec.price_per_hour_ev is None
    assert rec.price_max_minutes is None
    assert rec.residential_zone is None
    assert rec.night_parking_forbidden is None
    assert rec.total_spaces == 3
    assert rec.notes is None


def test_normalize_handles_unlimited_max_time() -> None:
    """pris_maks_tid='Ubegrenset' must become None, not 0."""
    feat = _økern_torgvei_feature()
    feat["properties"]["samferdsel.gisowner.parkering_pris.pris_maks_tid"] = "Ubegrenset"
    rec = normalize(feat)
    assert rec is not None and rec.price_max_minutes is None
