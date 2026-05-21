"""Ingest data from Statens vegvesen's Parkeringsregister.

The Parkeringsregister is the national registry of parking areas in Norway,
operated by Statens vegvesen. The read API is open (no auth, no API key).

Endpoint discovered via the live frontend at
https://www.vegvesen.no/trafikkinformasjon/reiseinformasjon/parkeringsregisteret:

    GET https://parkreg-open.atlas.vegvesen.no/ws/no/vegvesen/veg/
        parkeringsomraade/parkeringsregisteret/v1/parkeringsomraade/

A single call returns ALL parking areas (currently ~21k, of which ~10k
are active). The frontend filters client-side. We do the same.

This module:
  1. Fetches the full list.
  2. Saves the raw JSON payload to ``data/raw/``.
  3. Filters to active records whose ``poststed`` is Oslo (configurable).
  4. Writes a normalized CSV to ``data/normalized/parkeringsregister.csv``.

Run as a script:

    python -m parking_app.ingest.fetch_register
    # or, after `pip install -e .`:
    parking-ingest-register --help
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Iterable

import requests

from ..models import ParkingRecord
from ..storage import save_raw, write_normalized_csv

LOG = logging.getLogger("parking_app.ingest.fetch_register")

API_BASE = (
    "https://parkreg-open.atlas.vegvesen.no/ws/no/vegvesen/veg/"
    "parkeringsomraade/parkeringsregisteret/v1"
)
LIST_ENDPOINT = f"{API_BASE}/parkeringsomraade/"
DETAIL_ENDPOINT = f"{API_BASE}/parkeringsomraade/{{id}}"

SOURCE_TYPE = "parkeringsregister"
DEFAULT_USER_AGENT = "oslo-parking-finder/0.1 (+https://github.com/etmagnussen)"

# Default municipality filter. The API exposes ``poststed`` (post-town) rather
# than kommune, so we match on that. "OSLO" covers all postal areas inside
# Oslo kommune. See README "Antakelser" for details.
DEFAULT_MUNICIPALITY = "OSLO"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def fetch_all(timeout: float = 60.0, session: requests.Session | None = None) -> list[dict[str, Any]]:
    """Fetch all parking areas from the register.

    Returns the raw JSON list as Python objects. Raises on HTTP errors.
    """
    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
    sess.headers.setdefault("Accept", "application/json")

    LOG.info("GET %s", LIST_ENDPOINT)
    resp = sess.get(LIST_ENDPOINT, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(f"Unexpected response type from API: {type(data).__name__}")
    LOG.info("Fetched %d records", len(data))
    return data


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def is_active(item: dict[str, Any]) -> bool:
    """An item is active if ``deaktivert`` is null/missing."""
    return item.get("deaktivert") in (None, "")


def matches_municipality(item: dict[str, Any], municipality: str | None) -> bool:
    """Match by ``poststed`` (post-town). Case-insensitive.

    If ``municipality`` is falsy, all items match.
    """
    if not municipality:
        return True
    poststed = (item.get("poststed") or "").strip().upper()
    return poststed == municipality.strip().upper()


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize(item: dict[str, Any]) -> ParkingRecord:
    """Map a raw API item to ``ParkingRecord``.

    Notes / assumptions:
      * ``municipality`` is best-effort derived from ``poststed`` (post-town).
        The register does not expose kommune directly. For Oslo this is
        accurate because the post-town "OSLO" is used across the kommune.
      * ``address`` combines ``adresse`` + postnummer + poststed when present.
      * ``source_url`` points to the public detail endpoint for traceability.
    """
    raw_address = (item.get("adresse") or "").strip()
    postnummer = (item.get("postnummer") or "").strip()
    poststed = (item.get("poststed") or "").strip()

    address_parts = [raw_address]
    if postnummer or poststed:
        address_parts.append(f"{postnummer} {poststed}".strip())
    address = ", ".join(p for p in address_parts if p) or None

    item_id = item.get("id")
    source_url = DETAIL_ENDPOINT.format(id=item_id) if item_id is not None else LIST_ENDPOINT

    return ParkingRecord(
        name=(item.get("navn") or "").strip() or "(uten navn)",
        address=address,
        municipality=poststed.title() or None,  # "OSLO" -> "Oslo"
        lat=_to_float(item.get("breddegrad")),
        lon=_to_float(item.get("lengdegrad")),
        operator=(item.get("parkeringstilbyderNavn") or "").strip() or None,
        source_url=source_url,
        source_type=SOURCE_TYPE,
    )


def normalize_many(
    items: Iterable[dict[str, Any]],
    *,
    municipality: str | None = DEFAULT_MUNICIPALITY,
    only_active: bool = True,
) -> list[ParkingRecord]:
    out: list[ParkingRecord] = []
    for item in items:
        if only_active and not is_active(item):
            continue
        if not matches_municipality(item, municipality):
            continue
        out.append(normalize(item))
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run(municipality: str | None = DEFAULT_MUNICIPALITY, include_inactive: bool = False) -> dict[str, Any]:
    """Run the full ingest. Returns a small stats dict."""
    data = fetch_all()
    raw_path = save_raw(data, source=SOURCE_TYPE, ext="json")
    LOG.info("Saved raw payload to %s", raw_path)

    records = normalize_many(
        data, municipality=municipality, only_active=not include_inactive
    )
    csv_path = write_normalized_csv(records, source=SOURCE_TYPE)
    LOG.info("Wrote %d normalized records to %s", len(records), csv_path)

    return {
        "raw_path": str(raw_path),
        "csv_path": str(csv_path),
        "total_fetched": len(data),
        "normalized_count": len(records),
        "municipality": municipality,
        "include_inactive": include_inactive,
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument(
        "--municipality",
        default=DEFAULT_MUNICIPALITY,
        help=(
            "Filter by poststed (post-town), case-insensitive. "
            "Use --municipality '' to disable filtering. Default: OSLO."
        ),
    )
    p.add_argument(
        "--include-inactive",
        action="store_true",
        help="Also include deactivated parking areas in the normalized output.",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    municipality = args.municipality or None
    try:
        stats = run(municipality=municipality, include_inactive=args.include_inactive)
    except requests.RequestException as exc:
        LOG.error("HTTP error: %s", exc)
        return 2
    except Exception as exc:  # noqa: BLE001 — surface unexpected errors clearly
        LOG.exception("Ingest failed: %s", exc)
        return 1

    print(
        "OK: fetched {total_fetched} records, wrote {normalized_count} normalized rows.\n"
        "  raw:  {raw_path}\n"
        "  csv:  {csv_path}".format(**stats)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
