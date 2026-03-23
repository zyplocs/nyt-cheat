#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Set, Optional, List


PRUNE_DIR = Path(__file__).resolve().parent
DEFAULT_DICT = (PRUNE_DIR.parent / "english-words" / "words_alpha.txt").resolve()
DEFAULT_SYSTEM_DICT = Path("/usr/share/dict/words")


def read_words(path: Path) -> Set[str]:
    if not path.exists():
        sys.exit(f"Error: file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            return {line.strip().lower() for line in f if line.strip()}
    except Exception as e:
        sys.exit(f"Error reading {path}: {e}")


def parse_answers_str(s: str) -> Set[str]:
    s = s.strip()
    # Try JSON first
    try:
        data = json.loads(s)
        if isinstance(data, list):
            tokens = [str(x) for x in data]
        elif isinstance(data, str):
            tokens = [data]
        else:
            tokens = []
    except Exception:
        # Fallback: split by commas or any whitespace
        tokens = re.split(r"[\s,]+", s)
    out: Set[str] = set()
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        # strip surrounding non-letters, keep a-z only
        t = re.sub(r"^[^A-Za-z]+|[^A-Za-z]+$", "", t)
        t = t.lower()
        if t:
            out.add(t)
    return out


def write_words_atomic(path: Path, words: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file in the same directory for atomic replace
    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    ) as tmp:
        tmp_path = Path(tmp.name)
        for w in sorted(words):
            tmp.write(w + "\n")
    os.replace(tmp_path, path)


def backup_file(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(path.name + f".bak-{ts}")
    shutil.copy2(path, backup)
    return backup


def load_system_words(path: Optional[Path]) -> Set[str]:
    if path and path.exists():
        return read_words(path)
    return set()


def preview(title: str, items: Iterable[str], limit: int) -> None:
    items = sorted(items)
    count = len(items)
    print(f"\n{title}: {count}")
    if count == 0:
        return
    show = items[:limit]
    for w in show:
        print(f"  - {w}")
    if count > limit:
        print(f"  ... and {count - limit} more")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze and prune dictionary words using Spelling Bee outputs (bad/fake) and official answers. "
            "By default runs in dry-run mode to show what would change."
        )
    )
    # Inputs (files or date)
    parser.add_argument(
        "--date", 
        help="6-digit date token, e.g. 080925"
    )
    parser.add_argument(
        "--data-dir", 
        default=str(PRUNE_DIR), 
        help="Directory containing answers_*.txt, fakes_*.txt, output_*.txt (default: prune/)" 
    )
    parser.add_argument(
        "--bad", 
        help="Path to fakes_*.txt"
    )
    parser.add_argument(
        "--true", 
        help="Path to answers_*.txt"
    )
    parser.add_argument(
        "--output", 
        help="Path to output_*.txt; if provided with answers, fakes are computed in-memory"
    )

    # Inline answers
    parser.add_argument("--answers-str", help="Answers provided inline (JSON array, comma- or whitespace-separated)")
    parser.add_argument("--answers-stdin", action="store_true", help="Read answers from STDIN (one per line or pasted blob)")

    # Behavior and safety
    parser.add_argument(
        "--dict", 
        dest="dict_path", 
        default=str(DEFAULT_DICT), 
        help=f"Dictionary path (default: {DEFAULT_DICT})"
    )
    parser.add_argument(
        "--apply", 
        action="store_true", 
        help="Apply changes (otherwise dry-run)"
    )
    parser.add_argument(
        "--yes", "-y", 
        action="store_true", 
        help="Assume yes to prompts when applying"
    )
    parser.add_argument(
        "--no-add", 
        action="store_true", 
        help="Do not add missing true words to dictionary"
    )
    parser.add_argument(
        "--no-remove", 
        action="store_true", 
        help="Do not remove bad/fake words from dictionary"
    )
    parser.add_argument(
        "--conservative", 
        action="store_true", 
        help="Only remove words that are also NOT in a system dictionary (safer)"
    )
    parser.add_argument(
        "--system-dict", 
        default=str(DEFAULT_SYSTEM_DICT), 
        help="System dictionary to cross-check (default: /usr/share/dict/words if present)"
    )
    parser.add_argument(
        "--backup", "-B",
        action="store_true",
        help="Create a timestamped backup of the dictionary before applying changes"
    )
    parser.add_argument(
        "--show", 
        type=int, 
        default=20, 
        help="How many sample words to preview per category"
    )

    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir).resolve()
    dict_path = Path(args.dict_path).resolve()
    if not dict_path.exists():
        sys.exit(f"Error: dictionary not found: {dict_path}")

    # Determine answers
    answers_words: Set[str] = set()
    answers_source = ""
    if args.answers_str:
        answers_words = parse_answers_str(args.answers_str)
        answers_source = "--answers-str"
    elif args.answers_stdin:
        pasted = sys.stdin.read()
        answers_words = parse_answers_str(pasted)
        answers_source = "--answers-stdin"
    elif args.true:
        true_path = Path(args.true).resolve()
        answers_words = read_words(true_path)
        answers_source = str(true_path)
    elif args.date:
        if not (len(args.date) == 6 and args.date.isdigit()):
            sys.exit("Error: --date must be exactly 6 digits like 080925")
        true_path = (data_dir / f"answers_{args.date}.txt").resolve()
        answers_words = read_words(true_path)
        answers_source = str(true_path)

    # Determine bad/fake words
    bad_words: Set[str] = set()
    bad_source = ""
    output_words: Set[str] = set()
    if args.output:
        output_path = Path(args.output).resolve()
        output_words = read_words(output_path)
        output_words = {w for w in output_words if re.fullmatch(r"[a-z]+", w)}
        if answers_words:
            bad_words = output_words - answers_words
            bad_source = f"computed from {output_path} - {len(bad_words)}"
    if not bad_words:
        if args.bad:
            bad_path = Path(args.bad).resolve()
            bad_words = read_words(bad_path)
            bad_source = str(bad_path)
        elif args.date:
            if not (len(args.date) == 6 and args.date.isdigit()):
                sys.exit("Error: --date must be exactly 6 digits like 080925")
            bad_path = (data_dir / f"fakes_{args.date}.txt").resolve()
            bad_words = read_words(bad_path)
            bad_source = str(bad_path)

    # Load dictionary
    dict_words = read_words(dict_path)

    # Compute missing and removal candidates
    missing_words = set()
    if answers_words:
        missing_words = answers_words - dict_words
    removal_candidates = dict_words & bad_words

    # Conservative filter
    system_words: Set[str] = set()
    effective_conservative = False
    if args.conservative:
        sys_dict_path = Path(args.system_dict)
        if sys_dict_path.exists():
            system_words = load_system_words(sys_dict_path)
            effective_conservative = True
        else:
            print(f"Warning: system dictionary not found at {sys_dict_path}; proceeding without --conservative safeguard.")

    if effective_conservative:
        to_remove = {w for w in removal_candidates if w not in system_words}
    else:
        to_remove = set(removal_candidates)

    # Apply flags that disable actions
    if args.no_add:
        missing_words = set()
    if args.no_remove:
        to_remove = set()

    # Report inputs
    print("Inputs:")
    print(f"  Dictionary: {dict_path}")
    if bad_source:
        print(f"  Bad/Fakes : {bad_source}")
    else:
        print(f"  Bad/Fakes : (none provided; removals disabled or zero)")
    if answers_source:
        print(f"  Answers   : {answers_source}")
    else:
        print(f"  Answers   : (none provided; additions depend on fakes only)")
    if args.output:
        print(f"  Output    : {Path(args.output).resolve()}")
    if args.date:
        print(f"  Date token: {args.date}")
    print(f"  Data dir  : {data_dir}")

    # Analysis
    print("\nAnalysis:")
    print(f"  Dictionary size        : {len(dict_words):,}")
    print(f"  Bad/Fakes provided     : {len(bad_words):,}")
    print(f"  True answers provided  : {len(answers_words):,}")
    print(f"  Missing true in dict   : {len(missing_words):,}")
    print(f"  Removable candidates   : {len(removal_candidates):,}")
    if effective_conservative:
        print(f"  After conservative check: {len(to_remove):,} will be removed (only if not in system dict)")

    preview("Missing words to ADD", missing_words, args.show)
    preview("Bad words to REMOVE", to_remove, args.show)

    if not args.apply:
        print("\nDry-run mode: no changes written. Use --apply to make changes.")
        return 0

    # If apply, optionally prompt
    if not args.yes:
        proceed = input("\nApply these changes to the dictionary? [y/N]: ").strip().lower()
        if proceed not in {"y", "yes"}:
            print("Aborted by user. No changes made.")
            return 1

    # Build the new word set
    new_words = set(dict_words)
    if missing_words:
        new_words |= missing_words
    if to_remove:
        new_words -= to_remove

    if new_words == dict_words:
        print("\nNo changes necessary. Dictionary already up-to-date with provided inputs.")
        return 0

    # Backup if requested, then write atomically
    if args.backup:
        backup = backup_file(dict_path)
    write_words_atomic(dict_path, new_words)

    print("\nApplied changes:")
    if args.backup:
        print(f"  Backup created at: {backup}")
    print(f"  Added    : {len(missing_words):,}")
    print(f"  Removed  : {len(to_remove):,}")
    print(f"  New size : {len(new_words):,}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
