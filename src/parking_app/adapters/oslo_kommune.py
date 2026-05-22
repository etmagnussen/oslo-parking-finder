"""Oslo kommune / Bymiljøetaten adapter (geodata.bymoslo.no).

Oslo kommune publishes detailed on-street parking data via an open ArcGIS
REST endpoint hosted at ``https://geodata.bymoslo.no/``. The layer
``Parkering/MapServer/27`` is the gateparkering layer joined with pricing
data (``parkering_pris``) and is the primary source we use here.

The layer contains polygons for ~6 200 on-street parking sections in
Oslo, each with tariff group, prices for petrol/EV, residential zone,
night-parking flag, estimated number of spaces, and free-text remarks.
This is what we need to fix the "1 plass på Økern Torgvei"-problem:
Bymiljøetaten reports the real number per section, not just the count
of the surrounding Statens vegvesen polygon.

API contract (verified empirically):

* No auth, no API key.
* Native SR is EPSG:25832; pass ``outSR=4326`` to get WGS84 back.
* Max 2000 features per request; paginate via ``resultOffset``.
* ``f=geojson`` returns standard GeoJSON; we request that to avoid
  having to interpret Esri JSON ourselves.

Implementation choices (documented in PROJECT_NOTES.md, 2026-05-22 ADR):

* No ``pyproj`` dependency. We let the server reproject.
* Polygons are reduced to a representative point (centroid of the first
  ring) so the existing CSV ``lat``/``lon`` columns stay usable. The full
  geometry is intentionally NOT stored yet — that decision is deferred
  to a later ADR (spørsmål 1).
* Free fields like ``pris_bensin_diesel_hybrid`` are stored both
  as a parsed number (``price_per_hour_petrol``) and the source text is
  kept verbatim in ``notes`` if it contains additional context.

Run as a script:

    python -m parking_app.ingest.fetch_oslo_kommune
    # or use the adapter from Python:
    from parking_app.adapters.oslo_kommune import fetch
    records = fetch()
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

import requests

from ..models import ParkingRecord

LOG = logging.getLogger(__name__)

SOURCE_TYPE = "oslo_kommune_gateparkering"
DEFAULT_USER_AGENT = "oslo-parking-finder/0.1 (+https://github.com/etmagnussen)"

# Verified working endpoint (Parkering/MapServer/27 = gateparkering + priser).
LAYER_URL = (
    "https://geodata.bymoslo.no/arcgis/rest/services/geodata/"
    "Parkering/MapServer/27"
)
QUERY_URL = f"{LAYER_URL}/query"

# Oslo kommune bbox (a generous rectangle covering the entire municipality).
# lon_min, lat_min, lon_max, lat_max in WGS84.
OSLO_BBOX = (10.49, 59.81, 10.95, 60.13)

# ArcGIS REST hard cap; this layer does NOT support resultOffset pagination
# (advancedQueryCapabilities.supportsPagination=false). We use OBJECTID-based
# batching instead: first fetch all IDs, then POST queries in chunks.
# Batch size 1000 keeps the POST body comfortably small and stays under the
# layer's maxRecordCount of 2000 per response.
PAGE_SIZE = 1000

# Property names on this layer are fully qualified (Esri quirk):
#   ``str.gisowner.STR_Parkering.beregnet_antall``
#   ``samferdsel.gisowner.parkering_pris.pris_elbil``
# We do suffix matching to stay robust to schema renames upstream.


def _prop(props: dict[str, Any], suffix: str) -> Any:
    """Look up a property by its bare name, ignoring ArcGIS qualifier prefix."""
    target = suffix.lower()
    for key, value in props.items():
        # match either "foo.bar.<suffix>" or just "<suffix>"
        if key.lower() == target or key.lower().endswith("." + target):
            return value
    return None


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def _parse_number(value: Any) -> float | None:
    """Parse a number out of a value that may be int/float or '42 kr/time'.

    Returns ``None`` for empty, missing, or unparseable input.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    m = _NUMBER_RE.search(s.replace(",", "."))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _parse_int(value: Any) -> int | None:
    f = _parse_number(value)
    if f is None:
        return None
    return int(f)


def _parse_duration_minutes(value: Any) -> int | None:
    """Parse '2 timer', '30 min', '1 t' etc. into minutes.

    Returns ``None`` for empty, missing, or special tokens like 'Ubegrenset'
    (which means no time limit and should not be conflated with 0).
    Falls back to interpreting a bare number as minutes.
    """
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if "ubegrenset" in s or "ingen begrensning" in s:
        return None  # no time limit — use None to mean "unlimited"
    num = _parse_number(s)
    if num is None:
        return None
    if "time" in s or re.search(r"\bt\b", s) or re.search(r"\bh\b", s):
        return int(num * 60)
    # Default unit is minutes.
    return int(num)


_FIRST_HOUR_RE = re.compile(r"1\s*time\s+(\d+(?:[.,]\d+)?)\s*kr", re.IGNORECASE)


def _parse_first_hour_price(value: Any) -> float | None:
    """Parse the first-hour price out of a Bymiljøetaten tariff table string.

    The source format is
        '1 time 40 kr, 2 timer 81 kr, 3 timer 122 kr, 1 døgn 204 kr'
    so we anchor on '1 time NN kr'. If that pattern is missing, we fall
    back to ``_parse_number`` so a bare ``42`` still works (used by tests
    and by other layers that store a plain number).
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    m = _FIRST_HOUR_RE.search(s.replace(",", "."))
    # NOTE: we replace ',' for decimal handling. Norwegian uses ',' as both
    # decimal separator and list separator — but our regex requires 'kr'
    # right after the number, so this is safe.
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    # Fallback for simple numeric strings like '42' or '42 kr/time'.
    return _parse_number(s)


_TRUE_TOKENS = {"ja", "yes", "true", "1", "y"}
_FALSE_TOKENS = {"nei", "no", "false", "0", "n"}


def _parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if not s:
        return None
    if s in _TRUE_TOKENS:
        return True
    if s in _FALSE_TOKENS:
        return False
    return None


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _centroid_of_first_ring(geometry: dict[str, Any] | None) -> tuple[float | None, float | None]:
    """Compute a representative point as the average of a polygon ring's vertices.

    GeoJSON Polygon coords: ``[[[lon, lat], [lon, lat], ...]]``.
    MultiPolygon: ``[[[[lon, lat], ...]]]``.

    This is intentionally cheap — not a true centroid — but good enough
    to drop a marker on the map. For full accuracy we'd want polygons in
    Leaflet, which is the next ADR.
    """
    if not geometry:
        return None, None
    coords = geometry.get("coordinates")
    if not coords:
        return None, None

    gtype = geometry.get("type")
    if gtype == "Polygon":
        ring = coords[0] if coords else None
    elif gtype == "MultiPolygon":
        ring = coords[0][0] if coords and coords[0] else None
    elif gtype == "Point":
        return float(coords[0]), float(coords[1])
    else:
        return None, None

    if not ring:
        return None, None
    lons = [pt[0] for pt in ring if isinstance(pt, (list, tuple)) and len(pt) >= 2]
    lats = [pt[1] for pt in ring if isinstance(pt, (list, tuple)) and len(pt) >= 2]
    if not lons or not lats:
        return None, None
    return sum(lons) / len(lons), sum(lats) / len(lats)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _fetch_object_ids(
    sess: requests.Session,
    *,
    bbox: tuple[float, float, float, float] | None,
    timeout: float,
) -> tuple[list[int], str]:
    """Return ``(ids, oid_field_name)`` for all features matching the filter."""
    params: dict[str, str] = {
        "where": "1=1",
        "returnIdsOnly": "true",
        "f": "json",
    }
    if bbox is not None:
        lon_min, lat_min, lon_max, lat_max = bbox
        params.update(
            {
                "geometry": f"{lon_min},{lat_min},{lon_max},{lat_max}",
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
            }
        )
    resp = sess.get(QUERY_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    oid_field = data.get("objectIdFieldName") or "OBJECTID"
    ids = data.get("objectIds") or []
    return [int(x) for x in ids], oid_field


def _fetch_features_by_ids(
    sess: requests.Session,
    *,
    ids: list[int],
    oid_field: str,
    timeout: float,
) -> list[dict[str, Any]]:
    """Fetch GeoJSON features for a batch of object ids in a single request.

    We use POST because the ``where=OBJECTID IN (...)``-clause is too long
    for a URL when the batch contains hundreds of ids (server returns
    HTTP 414). ArcGIS REST treats POST and GET identically for /query.
    """
    if not ids:
        return []
    where = f"{oid_field} IN ({','.join(str(i) for i in ids)})"
    data = {
        "where": where,
        "outFields": "*",
        "outSR": "4326",
        "f": "geojson",
    }
    resp = sess.post(QUERY_URL, data=data, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("features") or []


def fetch_all(
    *,
    bbox: tuple[float, float, float, float] | None = OSLO_BBOX,
    page_size: int = PAGE_SIZE,
    timeout: float = 60.0,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Fetch all GeoJSON features for the layer (within bbox), in batches.

    Uses OBJECTID-based batching because the layer does not support
    ``resultOffset`` pagination. Returns a list of GeoJSON Feature dicts.
    Raises on HTTP errors.
    """
    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
    sess.headers.setdefault("Accept", "application/json")

    ids, oid_field = _fetch_object_ids(sess, bbox=bbox, timeout=timeout)
    LOG.info("Discovered %d object ids on %s", len(ids), LAYER_URL)

    all_features: list[dict[str, Any]] = []
    for batch_start in range(0, len(ids), page_size):
        batch = ids[batch_start : batch_start + page_size]
        LOG.info(
            "GET %s ids[%d:%d]", QUERY_URL, batch_start, batch_start + len(batch)
        )
        features = _fetch_features_by_ids(
            sess, ids=batch, oid_field=oid_field, timeout=timeout
        )
        all_features.extend(features)

    LOG.info("Fetched %d features from %s", len(all_features), LAYER_URL)
    return all_features


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize(feature: dict[str, Any]) -> ParkingRecord | None:
    """Map one GeoJSON feature to a ParkingRecord.

    Returns ``None`` if the feature has no usable coordinates. Property
    lookup goes through :func:`_prop` so the function works both with the
    real fully-qualified ArcGIS field names
    (``str.gisowner.STR_Parkering.beregnet_antall``) and with plain names
    in tests and other layers.
    """
    props = feature.get("properties") or {}
    geom = feature.get("geometry")
    lon, lat = _centroid_of_first_ring(geom)
    if lat is None or lon is None:
        return None

    # Layer 27 has no street-name field. We build a stable composite name
    # from the residential zone (if any) and OBJECTID so each record is
    # identifiable in the UI until we add reverse-geocoding later.
    zone = _clean_str(_prop(props, "beboerparkeringssone"))
    object_id = _prop(props, "objectid") or _prop(props, "globalid")
    name_explicit = _clean_str(_prop(props, "navn")) or _clean_str(_prop(props, "vegnavn"))
    if name_explicit:
        name = name_explicit
    elif zone:
        name = f"Gateparkering sone {zone}"
    else:
        name = "Gateparkering"
    if object_id is not None and not name_explicit:
        name = f"{name} #{object_id}"

    address = _clean_str(_prop(props, "adresse")) or _clean_str(_prop(props, "vegnavn"))

    beregnet = _prop(props, "beregnet_antall")
    befart = _prop(props, "befart_antall")
    total_spaces = _parse_int(beregnet if beregnet not in (None, "") else befart)

    notes = _clean_str(_prop(props, "fritekst"))

    source_url = f"{LAYER_URL}/{object_id}" if object_id is not None else LAYER_URL

    return ParkingRecord(
        name=name,
        address=address,
        municipality="Oslo",
        lat=lat,
        lon=lon,
        operator="Oslo kommune Bymiljøetaten",
        source_url=source_url,
        source_type=SOURCE_TYPE,
        tariff_group=_clean_str(_prop(props, "takstgruppe1")),
        price_per_hour_petrol=_parse_first_hour_price(_prop(props, "pris_bensin_diesel_hybrid")),
        price_per_hour_ev=_parse_first_hour_price(_prop(props, "pris_elbil")),
        price_max_minutes=_parse_duration_minutes(_prop(props, "pris_maks_tid")),
        price_active_hours=_clean_str(_prop(props, "pris_tidspunkt_du_må_betale")),
        residential_zone=zone,
        night_parking_forbidden=_parse_bool(_prop(props, "nattparkeringsforbud")),
        total_spaces=total_spaces,
        notes=notes,
    )


def normalize_many(features: Iterable[dict[str, Any]]) -> list[ParkingRecord]:
    out: list[ParkingRecord] = []
    for feat in features:
        rec = normalize(feat)
        if rec is not None:
            out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Public entry point used by the rest of the pipeline
# ---------------------------------------------------------------------------


def fetch() -> list[ParkingRecord]:
    """Fetch + normalize all Oslo kommune gateparkering features."""
    features = fetch_all()
    return normalize_many(features)
