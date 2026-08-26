#!/usr/bin/env python
"""Build the NER landslide training inventory from NASA COOLR (BUILD_PLAN.md task 1.12).

Reads the raw, global-scope COOLR "Reports" export (`data/static/COOLR_Reports_Points.csv` —
gitignored raw cache, obtained via a one-time manual Earthdata GIS portal export; see
Required_by_me.md and CLAUDE.md §12 2026-08-25 Session 2) and filters it down to India, further
restricted to the eight North-East India states (CLAUDE.md rule 9 — NER-first, no generic
pan-India model). Writes the filtered, cleaned subset to `data/static/ner_inventory.csv`.

GSI Bhukosh join (task 1.4's lithology layer) is explicitly SKIPPED this pass, not attempted —
task 1.4 was deliberately deferred by user decision to run last in Phase 1 (see BUILD_PLAN.md's
2026-08-25 note on task 1.4 and Required_by_me.md). If/when a GSI Bhukosh point export becomes
available, join it here by nearest-point or containment against `latitude`/`longitude`.

Why a committed, filtered CSV rather than a gitignored derived artifact: the raw global COOLR
export required a manual browser login+export (not re-fetchable by a script), and the India/NER
subset of it is small (~500 rows) — CLAUDE.md rule 15's "small vector files" exception is being
applied here; `.gitignore` carries an explicit exception for this one file. The raw 14k-row
global CSV stays gitignored — do not commit it, do not delete it (nothing regenerates it).

Usage:
    python -m ml.build_inventory
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]

RAW_COOLR_CSV = REPO_ROOT / "data" / "static" / "COOLR_Reports_Points.csv"
OUT_CSV = REPO_ROOT / "data" / "static" / "ner_inventory.csv"

# The eight North-East India states/UTs (CLAUDE.md §1/§7), matched against COOLR's
# `admin_division_name` field. Confirmed these are the exact strings COOLR uses (not e.g.
# "Arunanchal Pradesh", a typo that appears in some free-text `event_title`/`location_description`
# fields but NOT in `admin_division_name` — verified by inspecting the real value_counts()).
NER_STATES = [
    "Assam",
    "Arunachal Pradesh",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Sikkim",
    "Tripura",
]

OUTPUT_COLUMNS = [
    "objectid",
    "event_id",
    "event_date_ms",
    "event_dt",
    "event_title",
    "location_description",
    "landslide_category",
    "landslide_trigger",
    "landslide_size",
    "landslide_setting",
    "fatality_count",
    "injury_count",
    "latitude",
    "longitude",
    "location_accuracy",
    "country_code",
    "admin_division_name",
    "event_import_source",
]


def load_raw(path: Path = RAW_COOLR_CSV) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. This is the raw global COOLR export — it requires a manual "
            "Earthdata GIS portal login+export (see Required_by_me.md), it is NOT fetched by any "
            "script, and it is gitignored (never committed). If you have it elsewhere, copy it "
            "to this path before running ml/build_inventory.py."
        )
    return pd.read_csv(path, low_memory=False)


def filter_to_ner(df: pd.DataFrame) -> pd.DataFrame:
    """India rows, further restricted to the eight NER states. Drops rows with no usable
    coordinate (30 of the raw file's ~14.7k rows have null lat/lon globally — real, not a bug;
    COOLR allows a report with only a text location description and no geocoded point)."""
    india = df[df["country_code"] == "IN"]
    ner = india[india["admin_division_name"].isin(NER_STATES)].copy()
    before = len(ner)
    ner = ner.dropna(subset=["latitude", "longitude"])
    dropped = before - len(ner)
    if dropped:
        print(f"  dropped {dropped} NER row(s) with no geocoded lat/lon")
    return ner


def clean(ner: pd.DataFrame) -> pd.DataFrame:
    out = ner.copy()
    out["event_dt"] = pd.to_datetime(out["event_date"], unit="ms", errors="coerce")
    out = out.rename(columns={"event_date": "event_date_ms"})
    # Keep only the columns we actually use downstream — the raw file also carries source_link,
    # photo_link, comments, gazetteer_* fields etc. that add noise to a "small, committed" file.
    out = out[OUTPUT_COLUMNS]
    return out.sort_values("event_dt").reset_index(drop=True)


def build_inventory(raw_path: Path = RAW_COOLR_CSV, out_path: Path = OUT_CSV) -> pd.DataFrame:
    raw = load_raw(raw_path)
    print(f"Raw COOLR export: {len(raw)} rows (global scope)")

    india = raw[raw["country_code"] == "IN"]
    print(f"  India rows: {len(india)}")

    ner = filter_to_ner(raw)
    print(f"  NER rows (after state filter + coordinate drop): {len(ner)}")
    print("  By state:")
    for state, count in ner["admin_division_name"].value_counts().items():
        print(f"    {state}: {count}")
    print("  By location_accuracy:")
    for acc, count in ner["location_accuracy"].value_counts(dropna=False).items():
        print(f"    {acc}: {count}")

    cleaned = clean(ner)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(cleaned)} rows)")
    return cleaned


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", type=Path, default=RAW_COOLR_CSV, help="path to the raw global COOLR CSV")
    parser.add_argument("--out", type=Path, default=OUT_CSV, help="output path for the filtered NER inventory")
    args = parser.parse_args()
    build_inventory(args.raw, args.out)


if __name__ == "__main__":
    main()
