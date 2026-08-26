"""One-off generator for tests/fixtures/smap_synthetic_granule.h5 (task 1.10). Run manually with
`python tests/fixtures/_generate_smap_fixture.py` if the fixture ever needs regenerating (e.g. the
grid/values below change) — not imported or run automatically by the test suite, exactly like a
`scripts/` one-shot build script, kept here instead because it only ever produces a test fixture,
never a `data/` artifact.

Shape and values are synthetic (this session had no real granule to sample from — see smap.py's
module docstring) but built to the REAL documented SPL3SMP_E v5 structure (NSIDC User Guide):
Soil_Moisture_Retrieval_Data_AM/_PM groups, `soil_moisture`/`retrieval_qual_flag`/`latitude`/
`longitude` fields (PM suffixed `_pm`), Float32 -9999.0 fill value, Uint16 quality-flag bit 0.

4x4 grid with explicit per-cell coordinates chosen to sit safely inside or outside the real Aizawl
AOI bbox (92.60, 23.60, 92.85, 23.85) — SMAP's real 9km EASE-Grid 2.0 spacing is much finer than
this 4x4 fixture; the point here is exercising the PARSING/FILTERING logic, not being
geometrically faithful to a real EASE-Grid tile:
  - (0,0): fill value (-9999.0) in AM -> must be excluded.
  - (0,1): outside bbox (lon=92.50, west of min_lon=92.60) -> must be excluded.
  - (1,1): valid AM, recommended quality (qual bit0=0).
  - (1,2): valid AM but NOT recommended quality (qual bit0=1); PM at the same cell IS recommended
    -> exercises select_best_reading()'s AM-not-recommended vs PM-recommended tie-break (PM wins).
  - (2,2): AM is fill (-9999.0, retrieval skipped entirely that pass) but PM is valid+recommended
    -> exercises the "AM missing entirely, fall back to PM" path.
  - (3,3): valid in both AM and PM, both recommended -> AM should win (AM has priority).
  - all other cells: fill value in both AM and PM (typical of a mostly-ocean/no-data granule).
"""
from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

FIXTURE_PATH = Path(__file__).parent / "smap_synthetic_granule.h5"

FILL = -9999.0
SHAPE = (4, 4)
# The real Aizawl AOI bbox this fixture is designed against (backend/app/config.py):
# (min_lon=92.60, min_lat=23.60, max_lon=92.85, max_lat=23.85).

# lon/lat grid: explicit per-cell values (not a formula) so every cell used by a test sits safely
# INSIDE or safely OUTSIDE the bbox with a wide margin — a formula-generated grid hit float32
# rounding right at the bbox edge in an earlier version of this script (92.50 + 1*0.10 rounds to
# a hair under 92.60 in float32, silently dropping a cell meant to be included) and one row landed
# just past the bbox's northern edge (23.90 > max_lat=23.85) by construction error. Hardcoding
# avoids both classes of mistake instead of re-deriving safe arithmetic.
LON = np.full(SHAPE, FILL, dtype=np.float32)
LAT = np.full(SHAPE, FILL, dtype=np.float32)
_COORDS = {  # (row, col) -> (lon, lat), only for cells a test actually inspects
    (0, 0): (92.70, 23.70),  # fill in both AM/PM regardless of coords (see below)
    (0, 1): (92.40, 23.70),  # deliberately OUTSIDE bbox (lon well west of min_lon=92.60)
    (1, 1): (92.70, 23.70),  # clearly inside
    (1, 2): (92.75, 23.70),  # clearly inside
    (2, 2): (92.75, 23.75),  # clearly inside
    (3, 3): (92.80, 23.80),  # clearly inside
}
for (r, c), (lon, lat) in _COORDS.items():
    LON[r, c] = lon
    LAT[r, c] = lat
# Every other cell keeps LON=LAT=FILL (-9999.0) — fine, since SM_AM/SM_PM are fill there too, so
# these are excluded on the soil_moisture fill check before lon/lat would even matter.

SM_AM = np.full(SHAPE, FILL, dtype=np.float32)
SM_PM = np.full(SHAPE, FILL, dtype=np.float32)
QUAL_AM = np.full(SHAPE, 65534, dtype=np.uint16)  # NSIDC fill for the flag field
QUAL_PM = np.full(SHAPE, 65534, dtype=np.uint16)

# (1,1): AM valid + recommended.
SM_AM[1, 1] = 0.28
QUAL_AM[1, 1] = 0  # bit0=0 -> recommended

# (1,2): AM valid but NOT recommended; PM valid + recommended (PM should win).
SM_AM[1, 2] = 0.55
QUAL_AM[1, 2] = 1  # bit0=1 -> not recommended
SM_PM[1, 2] = 0.31
QUAL_PM[1, 2] = 0

# (2,2): AM missing (fill) entirely; PM valid + recommended (fallback path).
SM_PM[2, 2] = 0.19
QUAL_PM[2, 2] = 0

# (3,3): both AM and PM valid + recommended -> AM must win (priority order).
SM_AM[3, 3] = 0.40
QUAL_AM[3, 3] = 0
SM_PM[3, 3] = 0.90  # deliberately different so a test can prove AM (0.40), not PM, was picked
QUAL_PM[3, 3] = 0

# (0,0) stays fill in AM/PM (tests fill-value exclusion); (0,1) has real lon outside the Aizawl
# bbox (92.50 < 92.60) even though it otherwise has a "valid-looking" reading, to test bbox
# filtering independent of fill-value filtering.
SM_AM[0, 1] = 0.33
QUAL_AM[0, 1] = 0


def write_group(f: h5py.File, name: str, suffix: str, sm: np.ndarray, qual: np.ndarray) -> None:
    group = f.create_group(name)
    group.create_dataset(f"soil_moisture{suffix}", data=sm)
    group.create_dataset(f"retrieval_qual_flag{suffix}", data=qual)
    group.create_dataset(f"latitude{suffix}", data=LAT)
    group.create_dataset(f"longitude{suffix}", data=LON)


def main() -> None:
    with h5py.File(FIXTURE_PATH, "w") as f:
        write_group(f, "Soil_Moisture_Retrieval_Data_AM", "", SM_AM, QUAL_AM)
        write_group(f, "Soil_Moisture_Retrieval_Data_PM", "_pm", SM_PM, QUAL_PM)
    print(f"Wrote {FIXTURE_PATH} ({FIXTURE_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
