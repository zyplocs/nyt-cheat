#!/usr/bin/env bash
set -euo pipefail

# derive_fakes.sh [--data-dir DIR] DATE
# Produces fakes_DATE.txt by taking words in output_DATE.txt that are not in answers_DATE.txt

PRUNE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$PRUNE_DIR"
DATE=""

usage() {
  echo "Usage: $(basename "$0") [--data-dir DIR] DATE(6 digits)" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-dir)
      [[ $# -ge 2 ]] || usage
      DATA_DIR="$2"; shift 2 ;;
    -h|--help)
      usage ;;
    *)
      if [[ -z "$DATE" ]]; then
        DATE="$1"; shift
      else
        echo "Unexpected argument: $1" >&2; exit 2
      fi ;;
  esac
done

if [[ -z "$DATE" ]]; then
  usage
fi
if [[ ! "$DATE" =~ ^[0-9]{6}$ ]]; then
  echo "Error: DATE must be exactly 6 digits, e.g. 080925" >&2
  exit 2
fi

ANSWERS="${DATA_DIR%/}/answers_${DATE}.txt"
OUTPUT="${DATA_DIR%/}/output_${DATE}.txt"
FAKES="${DATA_DIR%/}/fakes_${DATE}.txt"

if [[ ! -f "$ANSWERS" ]]; then
  echo "Error: missing answers file: $ANSWERS" >&2
  exit 1
fi
if [[ ! -f "$OUTPUT" ]]; then
  echo "Error: missing output file: $OUTPUT" >&2
  exit 1
fi

# Create fakes by set-diff: OUTPUT minus ANSWERS
# Use LC_ALL=C sort -u for stable, fast sorting
LC_ALL=C comm -23 \
  <(LC_ALL=C sort -u "$OUTPUT") \
  <(LC_ALL=C sort -u "$ANSWERS") \
  > "$FAKES"

ADDED=$(wc -l < "$FAKES" | tr -d '[:space:]')
echo "Wrote $FAKES ($ADDED candidate fakes)"
