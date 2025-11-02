#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-smart_merge}"

ROOT_DIR="${ROOT_DIR:-/data}"
MASTER_DIR="${MASTER_DIR:-MobileBackup/Gremlin}"
SOURCE_DIR="${SOURCE_DIR:-Google Fotos}"
OUT_DIR="${OUT_DIR:-/out}"
QUAR_DIR="${QUAR_DIR:-/quarantine}"
DRY_RUN="${DRY_RUN:-1}"

PHASH_THRESHOLD="${PHASH_THRESHOLD:-8}"
EXTS="${EXTS:-jpg,jpeg,png,heic,heif,tif,tiff,cr2,cr3,nef,arw,dng,mp4,mov,m4v}"
QUALITY_ORDER="${QUALITY_ORDER:-raw,heic,jpeg,png,other}"

export ROOT_DIR MASTER_DIR SOURCE_DIR OUT_DIR QUAR_DIR DRY_RUN PHASH_THRESHOLD EXTS QUALITY_ORDER TZ

mkdir -p "$OUT_DIR"

case "$MODE" in
  smart_merge)
    # Plan (CSV) + report JSON
    python3 /app/similar.py plan || exit 1

    if [[ "$DRY_RUN" != "0" ]]; then
      echo "Dry-Run complete. Plan is in $OUT_DIR."
      exit 0
    fi

    # Execute plan (move/replace + quarantine)
    python3 /app/similar.py apply || exit 1
    ;;
  apply_only)
    # Only execute existing plan without recalculating
    python3 /app/similar.py apply || exit 1
    ;;
  *)
    echo "Usage: entrypoint.sh [smart_merge|apply_only]" >&2
    exit 2
    ;;
esac
