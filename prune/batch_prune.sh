#!/usr/bin/env bash
set -euo pipefail

# batch_prune.sh [--apply] [-y|--yes] [--conservative] [--regen-fakes] [--dict PATH] [--dates D1,D2,...] [--data-dir DIR]
# For each DATE with answers_DATE.txt and output_DATE.txt in the data dir, optionally (re)generate fakes_DATE.txt,
# then run pruner.py in dry-run by default or apply if --apply is specified.

PRUNE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="python3"
DATA_DIR="$PRUNE_DIR"

APPLY=0
YES=0
CONSERVATIVE=0
REGEN=0
DICT=""
DATES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    -y|--yes) YES=1; shift ;;
    --conservative) CONSERVATIVE=1; shift ;;
    --regen-fakes) REGEN=1; shift ;;
    --dict) DICT="$2"; shift 2 ;;
    --dates) DATES="$2"; shift 2 ;;
    --data-dir) DATA_DIR="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $(basename "$0") [--apply] [-y|--yes] [--conservative] [--regen-fakes] [--dict PATH] [--dates D1,D2,...] [--data-dir DIR]";
      exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Build the date list from DATA_DIR
mapfile -t ALL_ANSWERS < <(cd "$DATA_DIR" && ls -1 answers_*.txt 2>/dev/null || true)
if [[ ${#ALL_ANSWERS[@]} -eq 0 ]]; then
  echo "No answers_*.txt files found in $DATA_DIR" >&2
  exit 0
fi

extract_date() { basename "$1" | sed -E 's/^answers_([0-9]{6})\.txt$/\1/' ; }

DATES_ARRAY=()
if [[ -n "$DATES" ]]; then
  IFS=',' read -r -a DATES_ARRAY <<< "$DATES"
else
  for f in "${ALL_ANSWERS[@]}"; do
    d="$(extract_date "$f")"
    [[ -z "$d" ]] && continue
    if [[ -f "$DATA_DIR/output_${d}.txt" ]]; then
      DATES_ARRAY+=("$d")
    fi
  done
fi

if [[ ${#DATES_ARRAY[@]} -eq 0 ]]; then
  echo "No matching dates with both answers_*.txt and output_*.txt found in $DATA_DIR." >&2
  exit 0
fi

# Build pruner flags
PRUNER_FLAGS=("--data-dir" "$DATA_DIR")
if [[ $APPLY -eq 1 ]]; then PRUNER_FLAGS+=("--apply"); fi
if [[ $YES -eq 1 ]]; then PRUNER_FLAGS+=("--yes"); fi
if [[ $CONSERVATIVE -eq 1 ]]; then PRUNER_FLAGS+=("--conservative"); fi
if [[ -n "$DICT" ]]; then PRUNER_FLAGS+=("--dict" "$DICT"); fi

for d in "${DATES_ARRAY[@]}"; do
  echo "=== Date $d ==="
  if [[ $REGEN -eq 1 || ! -f "$DATA_DIR/fakes_${d}.txt" ]]; then
    "$PRUNE_DIR/derive_fakes.sh" --data-dir "$DATA_DIR" "$d"
  fi
  echo "Running pruner.py for $d ..."
  "$PY" "$PRUNE_DIR/pruner.py" --date "$d" "${PRUNER_FLAGS[@]}"
  echo
done

echo "Done."
