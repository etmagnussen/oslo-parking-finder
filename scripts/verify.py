"""Project-wide verification: structure, imports, tests, and CSV sanity.

Run from the project root:

    python scripts/verify.py

Designed to be cheap to re-run after any code change. Does NOT hit the
network — use ``parking-ingest-register`` for the live ingest, then run
this script to sanity-check the resulting CSV.

Exit code 0 on success, non-zero on the first failed step.
"""

from __future__ import annotations

import csv
import importlib
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "PROJECT_NOTES.md",
    "pyproject.toml",
    "src/parking_app/__init__.py",
    "src/parking_app/models.py",
    "src/parking_app/storage.py",
    "src/parking_app/ingest/__init__.py",
    "src/parking_app/ingest/fetch_register.py",
    "src/parking_app/adapters/__init__.py",
    "src/parking_app/adapters/onepark.py",
    "src/parking_app/adapters/aimopark.py",
    "src/parking_app/adapters/oslo_kommune.py",
    "data/raw/.gitkeep",
    "data/normalized/.gitkeep",
    "tests/.gitkeep",
]

# Header is sourced from the canonical FIELDS tuple so this script does not
# drift when the schema is extended (e.g. detail-ingest adds capacity fields).
# Imported lazily inside check_normalized_csv so the file-existence step can
# still surface missing-source-files cleanly.
EXPECTED_HEADER: list[str] | None = None

# Rough Oslo bounding box (WGS84): used as a smoke test, not a strict filter.
OSLO_BBOX = (59.80, 60.15, 10.45, 10.95)  # lat_min, lat_max, lon_min, lon_max


def step(name: str) -> None:
    print(f"\n== {name} " + "=" * max(0, 60 - len(name)))


def check_files() -> None:
    step("1. Required files")
    missing = [f for f in REQUIRED_FILES if not (ROOT / f).exists()]
    for f in REQUIRED_FILES:
        print(f"  {'OK ' if (ROOT / f).exists() else 'MISS'}  {f}")
    if missing:
        raise SystemExit(f"Missing files: {missing}")


def check_imports() -> None:
    step("2. Imports + stubs")
    sys.path.insert(0, str(ROOT / "src"))
    parking_app = importlib.import_module("parking_app")
    importlib.import_module("parking_app.models")
    importlib.import_module("parking_app.storage")
    importlib.import_module("parking_app.ingest.fetch_register")
    for name in ("onepark", "aimopark", "oslo_kommune"):
        mod = importlib.import_module(f"parking_app.adapters.{name}")
        try:
            mod.fetch()
        except NotImplementedError:
            print(f"  OK  {name}.fetch() raises NotImplementedError")
        else:
            raise SystemExit(f"{name}.fetch() should raise NotImplementedError")
    print(f"  version: {parking_app.__version__}")


def check_pytest() -> None:
    step("3. pytest")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"pytest failed (exit {result.returncode})")


def check_normalized_csv() -> None:
    step("4. Normalized CSV sanity (if present)")
    csv_path = ROOT / "data" / "normalized" / "parkeringsregister.csv"
    if not csv_path.exists():
        print(f"  SKIP  {csv_path} not found — run `parking-ingest-register` first.")
        return

    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    if not rows:
        raise SystemExit("CSV is empty")

    from parking_app.models import FIELDS  # local import; src already on sys.path

    header = list(rows[0].keys())
    expected = list(FIELDS)
    if header != expected:
        raise SystemExit(f"Header mismatch:\n  got:      {header}\n  expected: {expected}")

    bad_url = [r for r in rows if not re.search(r"/parkeringsomraade/\d+$", r["source_url"])]
    if bad_url:
        raise SystemExit(f"{len(bad_url)} rows have malformed source_url")

    with_coords = sum(1 for r in rows if r["lat"] and r["lon"])
    coord_pct = 100.0 * with_coords / len(rows)

    def _f(x: str) -> float | None:
        return float(x) if x else None

    inside = 0
    outside = 0
    for r in rows:
        lat, lon = _f(r["lat"]), _f(r["lon"])
        if lat is None or lon is None:
            continue
        if (OSLO_BBOX[0] <= lat <= OSLO_BBOX[1] and OSLO_BBOX[2] <= lon <= OSLO_BBOX[3]):
            inside += 1
        else:
            outside += 1

    print(f"  rows         : {len(rows)}")
    print(f"  with coords  : {with_coords} ({coord_pct:.1f} %)")
    print(f"  in Oslo bbox : {inside}   outside: {outside}")

    if coord_pct < 95.0:
        raise SystemExit(f"Coordinate coverage below 95%: {coord_pct:.1f}%")
    if outside > 0.05 * len(rows):
        raise SystemExit(f"Too many points outside Oslo bbox: {outside}")


def main() -> int:
    check_files()
    check_imports()
    check_pytest()
    check_normalized_csv()
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
