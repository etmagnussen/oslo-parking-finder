"""Enrich Parkeringsregister rows with per-facility detail.

The list endpoint used by :mod:`fetch_register` returns name, address,
coordinates and operator, but **not** capacity fields. The detail
endpoint exposes them under ``aktivVersjon``:

    antallAvgiftsbelagtePlasser   -> paid_spaces
    antallAvgiftsfriePlasser      -> free_spaces
    antallLadeplasser             -> charging_spaces
    antallForflytningshemmede     -> accessible_spaces
    typeParkeringsomrade          -> facility_type
    innfartsparkering             -> is_park_and_ride

Running this script:

  * fetches the list (or reuses a cached raw file),
  * picks the active records matching the municipality filter,
  * GETs the detail endpoint once per id,
  * caches each detail JSON on disk under ``data/raw/details/<id>.json``,
  * writes an enriched normalized CSV.

Rate limiting: a small sleep between requests (``--sleep``, default 0.05s)
keeps us friendly. Default polite User-Agent. The script is resumable —
on re-run, cached detail files are reused unless ``--refresh`` is given.

Usage::

    python -m parking_app.ingest.fetch_register_details
    parking-ingest-register-details --limit 50         # quick smoke test
    parking-ingest-register-details --refresh          # ignore cache
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import requests

from ..models import ParkingRecord
from ..storage import project_root, save_raw, write_normalized_csv
from . import fetch_register as fr

LOG = logging.getLogger("parking_app.ingest.fetch_register_details")

SOURCE_TYPE = fr.SOURCE_TYPE  # same canonical source as the list ingest


def details_cache_dir() -> Path:
    p = project_root() / "data" / "raw" / "details"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def fetch_detail(
    facility_id: int,
    *,
    session: requests.Session,
    use_cache: bool = True,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Fetch one facility detail, with disk cache."""
    cache_path = details_cache_dir() / f"{facility_id}.json"
    if use_cache and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    url = fr.DETAIL_ENDPOINT.format(id=facility_id)
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


# ---------------------------------------------------------------------------
# Merge: list row + detail -> ParkingRecord
# ---------------------------------------------------------------------------


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bool_ja_nei(value: Any) -> bool | None:
    if value is None:
        return None
    s = str(value).strip().upper()
    if s == "JA":
        return True
    if s == "NEI":
        return False
    return None


def enrich(list_item: dict[str, Any], detail: dict[str, Any]) -> ParkingRecord:
    """Build a ParkingRecord by combining a list item with its detail payload."""
    rec = fr.normalize(list_item)
    aktiv = detail.get("aktivVersjon") or {}

    rec.paid_spaces = _to_int(aktiv.get("antallAvgiftsbelagtePlasser"))
    rec.free_spaces = _to_int(aktiv.get("antallAvgiftsfriePlasser"))
    rec.charging_spaces = _to_int(aktiv.get("antallLadeplasser"))
    rec.accessible_spaces = _to_int(aktiv.get("antallForflytningshemmede"))
    rec.facility_type = (aktiv.get("typeParkeringsomrade") or None) or None
    rec.is_park_and_ride = _to_bool_ja_nei(aktiv.get("innfartsparkering"))
    return rec


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def enrich_many(
    list_items: Iterable[dict[str, Any]],
    *,
    use_cache: bool = True,
    sleep_seconds: float = 0.05,
    progress_every: int = 250,
    session: requests.Session | None = None,
) -> list[ParkingRecord]:
    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", fr.DEFAULT_USER_AGENT)
    sess.headers.setdefault("Accept", "application/json")

    out: list[ParkingRecord] = []
    items = list(list_items)
    for i, item in enumerate(items, 1):
        fid = item.get("id")
        if fid is None:
            continue
        try:
            detail = fetch_detail(fid, session=sess, use_cache=use_cache)
        except requests.RequestException as exc:
            LOG.warning("detail %s failed: %s — using list-only record", fid, exc)
            out.append(fr.normalize(item))
            continue
        out.append(enrich(item, detail))
        if progress_every and i % progress_every == 0:
            LOG.info("  enriched %d / %d", i, len(items))
        # Be polite — only sleep on a real HTTP call, not a cache hit.
        if sleep_seconds > 0 and not (
            use_cache and (details_cache_dir() / f"{fid}.json").exists()
        ):
            time.sleep(sleep_seconds)
    return out


def run(
    *,
    municipality: str | None = fr.DEFAULT_MUNICIPALITY,
    include_inactive: bool = False,
    limit: int | None = None,
    refresh: bool = False,
    sleep_seconds: float = 0.05,
) -> dict[str, Any]:
    list_items = fr.fetch_all()
    save_raw(list_items, source=SOURCE_TYPE, ext="json")

    selected = fr.filter_items(
        list_items, municipality=municipality, only_active=not include_inactive
    )
    if limit is not None:
        selected = selected[:limit]
    LOG.info("Enriching %d records (use_cache=%s)", len(selected), not refresh)

    records = enrich_many(
        selected, use_cache=not refresh, sleep_seconds=sleep_seconds
    )
    csv_path = write_normalized_csv(records, source=SOURCE_TYPE)

    free = sum(1 for r in records if (r.free_spaces or 0) > 0)
    charging = sum(1 for r in records if (r.charging_spaces or 0) > 0)
    accessible = sum(1 for r in records if (r.accessible_spaces or 0) > 0)
    park_and_ride = sum(1 for r in records if r.is_park_and_ride)

    return {
        "csv_path": str(csv_path),
        "fetched_list": len(list_items),
        "selected": len(selected),
        "enriched": len(records),
        "with_free_spaces": free,
        "with_charging": charging,
        "with_accessible": accessible,
        "park_and_ride": park_and_ride,
        "municipality": municipality,
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--municipality", default=fr.DEFAULT_MUNICIPALITY,
                   help="Filter by poststed. Use '' to disable.")
    p.add_argument("--include-inactive", action="store_true")
    p.add_argument("--limit", type=int, default=None,
                   help="Limit number of facilities (for quick smoke tests).")
    p.add_argument("--refresh", action="store_true",
                   help="Ignore disk cache and re-fetch every detail.")
    p.add_argument("--sleep", type=float, default=0.05,
                   help="Seconds to sleep between HTTP calls (cache hits skip).")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    municipality = args.municipality or None
    try:
        stats = run(
            municipality=municipality,
            include_inactive=args.include_inactive,
            limit=args.limit,
            refresh=args.refresh,
            sleep_seconds=args.sleep,
        )
    except requests.RequestException as exc:
        LOG.error("HTTP error: %s", exc)
        return 2
    except Exception as exc:  # noqa: BLE001
        LOG.exception("Enrich failed: %s", exc)
        return 1

    print(
        "OK: enriched {enriched}/{selected} records\n"
        "  with free spaces       : {with_free_spaces}\n"
        "  with charging          : {with_charging}\n"
        "  with accessible spots  : {with_accessible}\n"
        "  park & ride            : {park_and_ride}\n"
        "  csv                    : {csv_path}".format(**stats)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
