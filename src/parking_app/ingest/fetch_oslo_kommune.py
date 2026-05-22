"""Ingest Oslo kommune gateparkering data via geodata.bymoslo.no.

Fetches all features from the ArcGIS REST gateparkering+priser layer,
saves the raw GeoJSON to ``data/raw/``, and writes a normalized CSV to
``data/normalized/oslo_kommune_gateparkering.csv``.

Run:

    python -m parking_app.ingest.fetch_oslo_kommune
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

import requests

from ..adapters import oslo_kommune
from ..storage import save_raw, write_normalized_csv

LOG = logging.getLogger("parking_app.ingest.fetch_oslo_kommune")


def run() -> dict[str, Any]:
    """Run the full ingest. Returns a small stats dict."""
    features = oslo_kommune.fetch_all()
    raw_path = save_raw(
        {"type": "FeatureCollection", "features": features},
        source=oslo_kommune.SOURCE_TYPE,
        ext="json",
    )
    LOG.info("Saved raw payload to %s", raw_path)

    records = oslo_kommune.normalize_many(features)
    csv_path = write_normalized_csv(records, source=oslo_kommune.SOURCE_TYPE)
    LOG.info("Wrote %d normalized records to %s", len(records), csv_path)

    with_price = sum(1 for r in records if r.price_per_hour_petrol is not None)
    with_total = sum(1 for r in records if r.total_spaces is not None)
    return {
        "raw_path": str(raw_path),
        "csv_path": str(csv_path),
        "total_fetched": len(features),
        "normalized_count": len(records),
        "with_price": with_price,
        "with_total_spaces": with_total,
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    try:
        stats = run()
    except requests.RequestException as exc:
        LOG.error("HTTP error: %s", exc)
        return 2
    except Exception as exc:  # noqa: BLE001
        LOG.exception("Ingest failed: %s", exc)
        return 1

    print(
        "OK: fetched {total_fetched} features, wrote {normalized_count} normalized rows.\n"
        "  with price : {with_price}\n"
        "  with total : {with_total_spaces}\n"
        "  raw:  {raw_path}\n"
        "  csv:  {csv_path}".format(**stats)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
