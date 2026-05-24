"""Tests for the static map generator."""

from __future__ import annotations

from pathlib import Path

import pytest

from parking_app.web.build_map import (
    build_from_csv,
    classify,
    copy_static_assets,
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


def test_copy_static_assets_copies_nested_files(tmp_path: Path) -> None:
    static = tmp_path / "static"
    (static / "icons").mkdir(parents=True)
    (static / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    (static / "icons" / "icon-192.png").write_bytes(b"PNGSTUB")
    dest = tmp_path / "dist"
    copied = copy_static_assets(static, dest)
    assert {p.name for p in copied} == {"manifest.webmanifest", "icon-192.png"}
    assert (dest / "manifest.webmanifest").read_text(encoding="utf-8") == "{}"
    assert (dest / "icons" / "icon-192.png").read_bytes() == b"PNGSTUB"


def test_copy_static_assets_missing_dir_is_noop(tmp_path: Path) -> None:
    # Should not raise when the static dir doesn't exist.
    copied = copy_static_assets(tmp_path / "does_not_exist", tmp_path / "dist")
    assert copied == []


def test_build_from_csv_with_static_dir(tmp_path: Path) -> None:
    csv_path = tmp_path / "in.csv"
    csv_path.write_text(
        "name,address,municipality,lat,lon,operator,source_url,source_type,last_checked,"
        "paid_spaces,free_spaces,charging_spaces,accessible_spaces,facility_type,is_park_and_ride\n"
        "Test,Foo 1,Oslo,59.9,10.7,Op,https://x/1,parkeringsregister,"
        "2026-05-22T05:00:00+00:00,5,3,0,0,LANGS_KJOREBANE,False\n",
        encoding="utf-8",
    )
    static = tmp_path / "static"
    static.mkdir()
    (static / "manifest.webmanifest").write_text('{"name":"x"}', encoding="utf-8")
    out_path = tmp_path / "dist" / "index.html"
    stats = build_from_csv(csv_path, out_path, static_dir=static)
    assert stats["assets_copied"] == 1
    assert (out_path.parent / "manifest.webmanifest").exists()
    html = out_path.read_text(encoding="utf-8")
    assert 'rel="manifest"' in html


# ---------------------------------------------------------------------------
# Oslo kommune integration (pricing fields + multi-input)
# ---------------------------------------------------------------------------


def test_classify_with_price_per_hour() -> None:
    # When a price is provided, it overrides paid/free counts.
    assert classify(None, None, price_per_hour=42.0) == "paid"
    assert classify(None, None, price_per_hour=0.0) == "free"
    # price wins even if paid/free counts also exist
    assert classify(0, 5, price_per_hour=10.0) == "paid"


def test_csv_to_features_reads_oslo_kommune_pricing_fields() -> None:
    rows = [
        {
            "name": "Gateparkering sone 1 #123",
            "lat": "59.92", "lon": "10.78",
            "source_type": "oslo_kommune",
            "tariff_group": "sone 1",
            "price_per_hour_petrol": "40",
            "price_per_hour_ev": "20",
            "price_max_minutes": "120",
            "price_active_hours": "08-17 (man-fre)",
            "residential_zone": "1",
            "total_spaces": "5",
            "notes": "Avgift hverdager",
        }
    ]
    out = csv_to_features(rows)
    assert len(out) == 1
    f = out[0]
    assert f["category"] == "paid"  # price > 0 classifies as paid
    assert f["price_petrol"] == 40.0
    assert f["price_ev"] == 20.0
    assert f["price_max_min"] == 120
    assert f["active_hours"] == "08-17 (man-fre)"
    assert f["zone"] == "1"
    assert f["tariff"] == "sone 1"
    assert f["total"] == 5
    assert f["notes"] == "Avgift hverdager"
    assert f["source_type"] == "oslo_kommune"


def test_build_from_csv_merges_multiple_inputs(tmp_path: Path) -> None:
    """Multi-input: rows from both CSVs land in the same HTML, latest timestamp wins."""
    a = tmp_path / "register.csv"
    a.write_text(
        "name,lat,lon,source_type,source_url,last_checked,"
        "paid_spaces,free_spaces,is_park_and_ride\n"
        "P-hus A,59.91,10.74,parkeringsregister,https://x/1,"
        "2026-05-20T05:00:00+00:00,10,2,False\n",
        encoding="utf-8",
    )
    b = tmp_path / "oslo.csv"
    b.write_text(
        "name,lat,lon,source_type,source_url,last_checked,"
        "price_per_hour_petrol,price_per_hour_ev,residential_zone,total_spaces\n"
        "Gate B,59.93,10.78,oslo_kommune,https://geodata/27,"
        "2026-05-22T05:00:00+00:00,40,20,1,5\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.html"
    stats = build_from_csv([a, b], out)
    assert stats["features"] == 2
    assert stats["generated_at"] == "2026-05-22T05:00:00+00:00"
    assert stats["by_source"] == {str(a): 1, str(b): 1}
    html = out.read_text(encoding="utf-8")
    assert "P-hus A" in html and "Gate B" in html
    # Sidebar credits both sources now
    assert "Statens vegvesen" in html
    assert "Oslo kommune" in html
