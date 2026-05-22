"""Generate a self-contained Leaflet map HTML from the normalized CSV.

Usage:

    python -m parking_app.web.build_map
    parking-build-map --output data/normalized/oslo_parking_map.html

Design choices:

* **Self-contained** — one HTML file. Leaflet CSS/JS from CDN, data inlined
  as JSON. Open by double-clicking the file.
* **Cheap** — uses Leaflet's ``markerClusterGroup`` (CDN) so ~3k markers
  render smoothly on mobile.
* **Categorical colours**:
    - green  = only free spaces (paid == 0 and free > 0)
    - yellow = mixed (both paid and free spaces)
    - red    = only paid spaces (free == 0, paid > 0)
    - gray   = unknown / no capacity info
* **Google Maps deep link** on each popup:
  ``https://www.google.com/maps/dir/?api=1&destination={lat},{lon}``
* **Filters** in a side panel: only-free, has-charging, park-and-ride,
  accessible. Counter updates live.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Iterable

from ..storage import project_root

LOG = logging.getLogger("parking_app.web.build_map")

DEFAULT_INPUT = "data/normalized/parkeringsregister.csv"
DEFAULT_OUTPUT = "data/normalized/oslo_parking_map.html"

# Oslo city centre — used as initial map center.
OSLO_CENTER = (59.9139, 10.7522)
DEFAULT_ZOOM = 12


# ---------------------------------------------------------------------------
# Data shaping
# ---------------------------------------------------------------------------


def _to_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def classify(paid: int | None, free: int | None) -> str:
    """Categorise a facility by paid/free spaces."""
    if paid is None and free is None:
        return "unknown"
    p = paid or 0
    f = free or 0
    if p == 0 and f == 0:
        return "unknown"
    if p == 0 and f > 0:
        return "free"
    if f == 0 and p > 0:
        return "paid"
    return "mixed"


def csv_to_features(rows: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    """Project CSV rows into the compact JSON used by the map JS.

    Skips rows without coordinates — they can't be plotted.
    """
    features: list[dict[str, Any]] = []
    for r in rows:
        lat = _to_float(r.get("lat"))
        lon = _to_float(r.get("lon"))
        if lat is None or lon is None:
            continue

        paid = _to_int(r.get("paid_spaces"))
        free = _to_int(r.get("free_spaces"))
        charging = _to_int(r.get("charging_spaces"))
        accessible = _to_int(r.get("accessible_spaces"))
        pnr_raw = (r.get("is_park_and_ride") or "").strip().lower()
        pnr = True if pnr_raw == "true" else False if pnr_raw == "false" else None

        features.append(
            {
                "name": r.get("name") or "(uten navn)",
                "address": r.get("address") or "",
                "operator": r.get("operator") or "",
                "lat": lat,
                "lon": lon,
                "paid": paid,
                "free": free,
                "charging": charging,
                "accessible": accessible,
                "park_and_ride": pnr,
                "facility_type": r.get("facility_type") or "",
                "source_url": r.get("source_url") or "",
                "category": classify(paid, free),
            }
        )
    return features


# ---------------------------------------------------------------------------
# HTML template — a single self-contained page
# ---------------------------------------------------------------------------

# We use plain str.replace instead of str.format because the embedded
# JavaScript has ``{`` everywhere.
_HTML_TEMPLATE = r"""<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#2ecc71">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Parkering">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" type="image/png" sizes="192x192" href="icons/icon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="icons/icon-512.png">
<link rel="apple-touch-icon" sizes="192x192" href="icons/icon-192.png">
<title>Parkering i Oslo</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">
<style>
  html, body { margin: 0; height: 100%; font-family: -apple-system, system-ui, sans-serif;
                background: #fafafa; }
  /* Use dynamic viewport height so iOS Safari toolbar doesn't crop the map. */
  #app { display: flex; height: 100vh; height: 100dvh;
         padding: env(safe-area-inset-top) env(safe-area-inset-right)
                  env(safe-area-inset-bottom) env(safe-area-inset-left);
         box-sizing: border-box; }
  #sidebar {
    width: 280px; padding: 14px 16px; box-sizing: border-box;
    border-right: 1px solid #ddd; background: #fafafa; overflow-y: auto;
  }
  #sidebar h1 { font-size: 16px; margin: 0 0 8px; }
  #sidebar p.lead { font-size: 12px; color: #555; margin: 0 0 12px; }
  #sidebar label { display: block; margin: 8px 0; font-size: 14px; }
  #counter { font-weight: 600; margin: 12px 0 8px; }
  .legend { font-size: 12px; line-height: 1.6; }
  .swatch {
    display: inline-block; width: 12px; height: 12px;
    border-radius: 50%; margin-right: 6px; vertical-align: middle;
    border: 1px solid rgba(0,0,0,.2);
  }
  .swatch.free    { background: #2ecc71; }
  .swatch.mixed   { background: #f1c40f; }
  .swatch.paid    { background: #e74c3c; }
  .swatch.unknown { background: #95a5a6; }
  #map { flex: 1; }
  .popup-title { font-weight: 600; margin-bottom: 4px; }
  .popup-meta  { font-size: 12px; color: #555; margin-bottom: 6px; }
  .popup-stats { font-size: 13px; margin: 6px 0; }
  .popup-stats span { display: inline-block; margin-right: 10px; }
  .popup-links a { display: block; margin-top: 4px; font-size: 13px; }
  @media (max-width: 700px) {
    #app { flex-direction: column; }
    #sidebar { width: 100%; max-height: 45vh; border-right: 0; border-bottom: 1px solid #ddd; }
  }
</style>
</head>
<body>
<div id="app">
  <aside id="sidebar">
    <h1>Parkering i Oslo</h1>
    <p class="lead">Kilde: Statens vegvesen — Parkeringsregisteret. Sist beriket: __GENERATED_AT__.</p>

    <div class="legend">
      <div><span class="swatch free"></span>kun gratis-plasser</div>
      <div><span class="swatch mixed"></span>blanding av gratis og avgift</div>
      <div><span class="swatch paid"></span>kun avgift</div>
      <div><span class="swatch unknown"></span>ukjent kapasitet</div>
    </div>

    <div id="counter">— anlegg synlige</div>

    <label><input type="checkbox" id="f-free"> Bare med gratis-plasser</label>
    <label><input type="checkbox" id="f-charging"> Har ladeplass</label>
    <label><input type="checkbox" id="f-pnr"> Innfartsparkering</label>
    <label><input type="checkbox" id="f-accessible"> HC-plass</label>

    <p style="font-size:11px;color:#888;margin-top:18px;">
      Klikk en markør for detaljer og veibeskrivelse.
    </p>
  </aside>
  <div id="map"></div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
const FEATURES = __FEATURES_JSON__;
const CENTER = __CENTER_JSON__;
const ZOOM = __ZOOM__;

const CATEGORY_COLORS = {
  free:    "#2ecc71",
  mixed:   "#f1c40f",
  paid:    "#e74c3c",
  unknown: "#95a5a6",
};

function makeIcon(category) {
  const color = CATEGORY_COLORS[category] || CATEGORY_COLORS.unknown;
  return L.divIcon({
    className: "parking-marker",
    html: '<div style="background:' + color + ';width:14px;height:14px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 2px rgba(0,0,0,.4);"></div>',
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

function popupHtml(f) {
  const gmaps = "https://www.google.com/maps/dir/?api=1&destination=" + f.lat + "," + f.lon;
  const stats = [];
  if (f.free !== null && f.free !== undefined) stats.push("Gratis: <b>" + f.free + "</b>");
  if (f.paid !== null && f.paid !== undefined) stats.push("Avgift: <b>" + f.paid + "</b>");
  if (f.charging) stats.push("Lade: " + f.charging);
  if (f.accessible) stats.push("HC: " + f.accessible);
  return (
    '<div class="popup-title">' + escapeHtml(f.name) + "</div>" +
    '<div class="popup-meta">' + escapeHtml(f.operator || "") +
      (f.address ? " · " + escapeHtml(f.address) : "") + "</div>" +
    (stats.length ? '<div class="popup-stats">' + stats.join(" ") + "</div>" : "") +
    '<div class="popup-links">' +
      '<a href="' + gmaps + '" target="_blank" rel="noopener">Veibeskrivelse i Google Maps →</a>' +
      (f.source_url ? '<a href="' + f.source_url + '" target="_blank" rel="noopener">Detaljer hos Statens vegvesen →</a>' : "") +
    "</div>"
  );
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

const map = L.map("map", { preferCanvas: true }).setView(CENTER, ZOOM);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors',
}).addTo(map);

const cluster = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 40 });
const markers = FEATURES.map(f => {
  const m = L.marker([f.lat, f.lon], { icon: makeIcon(f.category) });
  m.bindPopup(() => popupHtml(f));
  m.feature = f;
  return m;
});

const filters = {
  free:       document.getElementById("f-free"),
  charging:   document.getElementById("f-charging"),
  pnr:        document.getElementById("f-pnr"),
  accessible: document.getElementById("f-accessible"),
};

function matches(f) {
  if (filters.free.checked       && !(f.free && f.free > 0)) return false;
  if (filters.charging.checked   && !(f.charging && f.charging > 0)) return false;
  if (filters.pnr.checked        && !f.park_and_ride) return false;
  if (filters.accessible.checked && !(f.accessible && f.accessible > 0)) return false;
  return true;
}

function refresh() {
  cluster.clearLayers();
  const visible = markers.filter(m => matches(m.feature));
  cluster.addLayers(visible);
  document.getElementById("counter").textContent =
    visible.length.toLocaleString("no") + " anlegg synlige (av " +
    FEATURES.length.toLocaleString("no") + ")";
}

Object.values(filters).forEach(el => el.addEventListener("change", refresh));
map.addLayer(cluster);
refresh();
</script>
</body>
</html>
"""


def render_html(features: list[dict[str, Any]], generated_at: str) -> str:
    """Inject features and metadata into the HTML template."""
    payload = json.dumps(features, ensure_ascii=False, separators=(",", ":"))
    return (
        _HTML_TEMPLATE
        .replace("__FEATURES_JSON__", payload)
        .replace("__CENTER_JSON__", json.dumps(list(OSLO_CENTER)))
        .replace("__ZOOM__", str(DEFAULT_ZOOM))
        .replace("__GENERATED_AT__", generated_at)
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def copy_static_assets(static_dir: Path, dest_dir: Path) -> list[Path]:
    """Copy PWA assets (manifest, icons) next to the generated HTML.

    Returns the list of destination paths written. Missing source files
    are skipped silently so the build doesn't break when icons haven't
    been generated yet.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    if not static_dir.exists():
        return copied
    for src in static_dir.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(static_dir)
        dst = dest_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(dst)
    return copied


def build_from_csv(
    input_path: Path,
    output_path: Path,
    *,
    static_dir: Path | None = None,
) -> dict[str, Any]:
    if not input_path.exists():
        raise FileNotFoundError(
            f"Normalized CSV not found: {input_path}. "
            "Run `parking-ingest-register-details` first."
        )
    with input_path.open(encoding="utf-8") as fh:
        features = csv_to_features(csv.DictReader(fh))

    # Use the most recent last_checked timestamp from the CSV as "generated_at".
    # Fall back to "ukjent" if missing.
    with input_path.open(encoding="utf-8") as fh:
        ts = max(
            (r.get("last_checked", "") for r in csv.DictReader(fh)),
            default="",
        )
    generated_at = ts or "ukjent"

    html = render_html(features, generated_at)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    assets: list[Path] = []
    if static_dir is not None:
        assets = copy_static_assets(static_dir, output_path.parent)

    by_cat: dict[str, int] = {}
    for f in features:
        by_cat[f["category"]] = by_cat.get(f["category"], 0) + 1
    return {
        "input": str(input_path),
        "output": str(output_path),
        "features": len(features),
        "by_category": by_cat,
        "generated_at": generated_at,
        "assets_copied": len(assets),
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--input", default=DEFAULT_INPUT,
                   help=f"Normalized CSV input. Default: {DEFAULT_INPUT}")
    p.add_argument("--output", default=DEFAULT_OUTPUT,
                   help=f"HTML output path. Default: {DEFAULT_OUTPUT}")
    p.add_argument("--static-dir", default=None,
                   help="Optional dir whose contents (manifest, icons) are copied "
                        "next to the generated HTML. Required for PWA install.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    root = project_root()
    in_path = (root / args.input) if not Path(args.input).is_absolute() else Path(args.input)
    out_path = (root / args.output) if not Path(args.output).is_absolute() else Path(args.output)
    static_dir: Path | None = None
    if args.static_dir is not None:
        s = Path(args.static_dir)
        static_dir = s if s.is_absolute() else (root / s)

    stats = build_from_csv(in_path, out_path, static_dir=static_dir)
    print(
        "OK: {features} markers written to {output}\n"
        "  by category: {by_category}\n"
        "  generated_at: {generated_at}\n"
        "  assets copied: {assets_copied}".format(**stats)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
