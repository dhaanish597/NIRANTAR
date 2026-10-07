#!/usr/bin/env bash
# Package the runtime + build-time data that CLAUDE.md rule 15 keeps OUT of git, so a deployed
# build can reconstitute it.
#
# Why this exists at all: `data/models/*`, `data/static/<aoi>/`, `data/osm/*` and `data/tiles/*`
# are gitignored by design (they are derived artifacts, some of them tens of megabytes). That is
# correct for the repository and fatal for a deployment, which has no `scripts/` run beforehand.
# The bundle is published as a GitHub Release asset — a public, unauthenticated, CDN-backed URL
# that does not pollute git history and does not require Docker (whose daemon is not available in
# this environment). `scripts/fetch_deploy_data.sh` is the other half.
#
# Deterministic-ish by construction: the file LIST is fixed here rather than `find`-ing a
# directory, so a stray file in data/ cannot silently change the bundle. The tarball is written
# with `--sort=name --mtime` so re-running with unchanged inputs produces a byte-identical archive
# and therefore an unchanged checksum.
#
# Usage: bash scripts/build_deploy_bundle.sh [output_dir]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$REPO_ROOT/dist-deploy}"
BUNDLE_NAME="nirantar-deploy-data-v1.tar.gz"

cd "$REPO_ROOT"

# The exact set `scripts/demo_check.py::_required_files()` validates, plus model_metadata.json.
# Kept in sync with that function deliberately — if they drift, `make demo-check` passes locally
# while the deployment is missing a file.
AOIS="aizawl wayanad tupul"
FILES=(
  "data/models/xgb_terrain_v1.json"
  "data/models/model_metadata.json"
)
for aoi in $AOIS; do
  FILES+=(
    "data/static/$aoi/dem.tif"
    "data/static/$aoi/cells.gpkg"
    "data/static/$aoi/exposure.gpkg"
    "data/osm/${aoi}_graph.pkl"
    "data/tiles/$aoi.pmtiles"
    "data/tiles/$aoi-hillshade.png"
  )
done

missing=()
for f in "${FILES[@]}"; do
  if [ ! -s "$f" ]; then
    missing+=("$f")
  fi
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "ERROR: refusing to build an incomplete bundle. Missing or empty:" >&2
  printf '  %s\n' "${missing[@]}" >&2
  echo >&2
  echo "Regenerate them first (see CLAUDE.md §11): scripts/fetch_dem.py, build_grid.py," >&2
  echo "fetch_exposure.py, build_road_graph.py, build_tiles.py, python -m ml.train --aoi aizawl" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

# --sort=name + a fixed --mtime make the archive reproducible; without them tar embeds each file's
# real mtime and the checksum changes on every run, which would make the pinned hash in
# fetch_deploy_data.sh meaningless.
tar --sort=name \
    --mtime='UTC 2026-01-01' \
    --owner=0 --group=0 --numeric-owner \
    -czf "$OUT_DIR/$BUNDLE_NAME" "${FILES[@]}"

if command -v sha256sum >/dev/null 2>&1; then
  ( cd "$OUT_DIR" && sha256sum "$BUNDLE_NAME" | tee "$BUNDLE_NAME.sha256" )
else
  # macOS / Git-Bash-without-coreutils fallback.
  ( cd "$OUT_DIR" && shasum -a 256 "$BUNDLE_NAME" | tee "$BUNDLE_NAME.sha256" )
fi

echo
echo "Wrote $OUT_DIR/$BUNDLE_NAME ($(du -h "$OUT_DIR/$BUNDLE_NAME" | cut -f1))"
echo "Publish it with:"
echo "  gh release create deploy-data-v1 \"$OUT_DIR/$BUNDLE_NAME\" --title 'Deployment data v1' --notes '...'"
