"""Tests for the static map generator."""

from __future__ import annotations

from pathlib import Path

import pytest

from parking_app.web.build_map import (
    build_from_csv,
    classify,
    csv_to_features,
    render_html,
)


def test_classify() -> None:
    assert classify(None, None) == "unknown"
    assert classify(0, 0) == "unknown"
    assert classify(0, 5) == "free"
    assert classify(5, 0) == "paid"
    assert classify(3, 2) == "mixed"
    assert classify(None, 4) == "free"
    assert classify(4, None) == "paid"


def test_csv_to_features_skips_rows_without_coords() -> None:
    rows = [
        {"name": "A", "lat": "59.9", "lon": "10.7", "paid_spaces": "5", "free_spaces": "3",
         "charging_spaces": "1", "accessible_spaces": "", "is_park_and_ride": "False",
         "facility_type": "PARKERINGSHUS", "source_url": "https://x/1",
         "operator": "Op", "address": "Foo 1"},
        {"name": "B no coords", "lat": "", "lon": "", "paid_spaces": "", "free_spaces": "",
         "charging_spaces": "", "accessible_spaces": "", "is_park_and_ride": "",
         "facility_type": "", "source_url": "", "operator": "", "address": ""},
        {"name": "C P&R", "lat": "59.95", "lon": "10.8", "paid_spaces": "0", "free_spaces": "20",
         "charging_spaces": "0", "accessible_spaces": "0", "is_park_and_ride": "True",
         "facility_type": "AVGRENSET_OMRADE", "source_url": "https://x/3",
         "operator": "OK", "address": "Bar 2"},
    ]
    out = csv_to_features(rows)
    assert len(out) == 2
    a, c = out
    assert a["category"] == "mixed"
    assert a["free"] == 3 and a["paid"] == 5
    assert c["category"] == "free"
    assert c["park_and_ride"] is True
    assert c["facility_type"] == "AVGRENSET_OMRADE"


def test_render_html_inlines_features_and_template() -> None:
    features = [{
        "name": "Maridalsveien 10", "address": "Maridalsveien 10, 0178 OSLO",
        "operator": "P-NORGE AS", "lat": 59.92, "lon": 10.75,
        "paid": 7, "free": 3, "charging": 0, "accessible": 1,
        "park_and_ride": False, "facility_type": "LANGS_KJOREBANE",
        "source_url": "https://example.test/32771", "category": "mixed",
    }]
    html = render_html(features, generated_at="2026-05-22T05:00:00+00:00")
    assert "Parkering i Oslo" in html
    assert "leaflet@1.9.4" in html  # CDN reference
    assert "google.com/maps/dir/" in html  # deep-link helper present
    assert "Maridalsveien 10" in html  # feature inlined
    assert "2026-05-22T05:00:00+00:00" in html
    # Placeholders fully substituted
    for placeholder in ("__FEATURES_JSON__", "__CENTER_JSON__",
                        "__ZOOM__", "__GENERATED_AT__"):
        assert placeholder not in html, f"Unfilled placeholder: {placeholder}"


def test_build_from_csv_roundtrip(tmp_path: Path) -> None:
    csv_path = tmp_path / "in.csv"
    out_path = tmp_path / "out.html"
    csv_path.write_text(
        "name,address,municipality,lat,lon,operator,source_url,source_type,last_checked,"
        "paid_spaces,free_spaces,charging_spaces,accessible_spaces,facility_type,is_park_and_ride\n"
        "Test,Foo 1,Oslo,59.9,10.7,Op,https://x/1,parkeringsregister,"
        "2026-05-22T05:00:00+00:00,5,3,0,0,LANGS_KJOREBANE,False\n",
        encoding="utf-8",
    )
    stats = build_from_csv(csv_path, out_path)
    assert stats["features"] == 1
    assert stats["by_category"] == {"mixed": 1}
    assert out_path.exists()
    html = out_path.read_text(encoding="utf-8")
    assert "Test" in html and "59.9" in html


def test_build_from_csv_missing_input_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_from_csv(tmp_path / "missing.csv", tmp_path / "out.html")
