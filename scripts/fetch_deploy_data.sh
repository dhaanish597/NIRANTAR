#!/usr/bin/env bash
# Fetch and unpack the gitignored data artifacts a deployed build needs (the other half of
# scripts/build_deploy_bundle.sh — read that file's header first for why this indirection exists).
#
# Runs at BUILD time on the host (Render's build command, Vercel's build command), never at
# request time, and never during a demo: CLAUDE.md rule 10 ("the demo must run with the network
# cable unplugged") is about the running demo, and a build that cannot reach the network is a
# build that was never going to produce a working image. The RUNNING service still makes no
# outbound call on the demo path.
#
# Idempotent and cheap when it has already run: every required file is checked first, and a
# complete tree short-circuits before any network access. That matters on Render, whose build
# cache survives between deploys only for the repo, not for gitignored paths — so this usually
# does download. Locally it means a second `make`-ish invocation is instant.
#
# Usage: bash scripts/fetch_deploy_data.sh
#   NIRANTAR_DEPLOY_DATA_URL  override the bundle URL (e.g. a local file:// path for testing)
#   NIRANTAR_DEPLOY_DATA_SHA256  override the pinned checksum (REQUIRED if the URL is overridden)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BUNDLE_URL="${NIRANTAR_DEPLOY_DATA_URL:-https://github.com/dhaanish597/NIRANTAR/releases/download/deploy-data-v1/nirantar-deploy-data-v1.tar.gz}"

# Integrity pin. The bundle is fetched over the network and unpacked over the working tree, so it
# is treated as untrusted input: a checksum published in git (here) and compared after download
# is the cheapest way to make a tampered or truncated asset fail loudly instead of half-extracting
# over good files. If you re-cut the bundle, update BOTH this hash and the URL's tag.
BUNDLE_SHA256="${NIRANTAR_DEPLOY_DATA_SHA256:-d24c14d63eef62a926db188906809306e2bb7ec2b1471adaebf9e6712368084a}"

AOIS="aizawl wayanad tupul"
REQUIRED=(
  "data/models/xgb_terrain_v1.json"
  "data/models/model_metadata.json"
)
for aoi in $AOIS; do
  REQUIRED+=(
    "data/static/$aoi/dem.tif"
    "data/static/$aoi/cells.gpkg"
    "data/static/$aoi/exposure.gpkg"
    "data/osm/${aoi}_graph.pkl"
    "data/tiles/$aoi.pmtiles"
    "data/tiles/$aoi-hillshade.png"
  )
done

complete=1
for f in "${REQUIRED[@]}"; do
  if [ ! -s "$f" ]; then
    complete=0
    break
  fi
done

if [ "$complete" -eq 1 ]; then
  echo "[deploy-data] all ${#REQUIRED[@]} artifacts already present — nothing to fetch."
  exit 0
fi

if [ "$BUNDLE_SHA256" = "__PINNED_SHA256__" ]; then
  echo "ERROR: BUNDLE_SHA256 is not pinned yet in scripts/fetch_deploy_data.sh." >&2
  echo "       Publish the bundle, then paste the hash from build_deploy_bundle.sh's output." >&2
  exit 1
fi
tmp_dir="$(mktemp -d)"
# shellcheck disable=SC2064  # expand tmp_dir now, not at trap-run time
trap "rm -rf '$tmp_dir'" EXIT

bundle="$tmp_dir/bundle.tar.gz"
echo "[deploy-data] downloading $BUNDLE_URL"
# -f turns an HTTP error into an error instead of quietly saving an HTML error page as the
# archive. --retry (without --retry-all-errors) retries exactly the transient classes — 408/429/
# 5xx, timeouts, connection resets — so a mistyped tag or a deleted release fails immediately with
# curl's real error, instead of looking like a slow network for 15 seconds.
curl -fL --retry 5 --retry-delay 3 --connect-timeout 30 -o "$bundle" "$BUNDLE_URL"

if command -v sha256sum >/dev/null 2>&1; then
  actual_sha256="$(sha256sum "$bundle" | cut -d' ' -f1)"
else
  actual_sha256="$(shasum -a 256 "$bundle" | cut -d' ' -f1)"
fi

if [ "$actual_sha256" != "$BUNDLE_SHA256" ]; then
  echo "ERROR: bundle checksum mismatch — refusing to extract." >&2
  echo "  expected: $BUNDLE_SHA256" >&2
  echo "  actual:   $actual_sha256" >&2
  exit 1
fi
echo "[deploy-data] checksum verified."

# Extract into a staging dir first, then move, so a corrupt archive cannot leave a half-written
# `data/` behind. Every path in the archive is relative to the repo root (see the build script).
stage="$tmp_dir/stage"
mkdir -p "$stage"
tar -xzf "$bundle" -C "$stage"

for f in "${REQUIRED[@]}"; do
  if [ ! -s "$stage/$f" ]; then
    echo "ERROR: verified archive is missing $f — bundle and script disagree." >&2
    exit 1
  fi
done

# tar -C stage . would also work, but copying the known list keeps this from ever creating a path
# the script did not explicitly ask for.
for f in "${REQUIRED[@]}"; do
  mkdir -p "$(dirname "$f")"
  cp "$stage/$f" "$f"
done

echo "[deploy-data] unpacked ${#REQUIRED[@]} artifacts into $REPO_ROOT/data"
