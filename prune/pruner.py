#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import stat
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
    except (OSError, UnicodeDecodeError) as e:
        sys.exit(f"Error reading {path}: {e}")


def parse_answers_str(s: str) -> Set[str]:
    s = s.strip()
    # Tables contain metadata that must never become dictionary entries.
    if re.search(r"(?m)^\s*[\"']?[A-Za-z]+[ \t]+(?:[0-9]+|pangram)\b", s, re.IGNORECASE):
        if __package__:
            from .transform_text import parse_word_block
        else:
            from transform_text import parse_word_block
        return set(parse_word_block(s))
    # Try JSON first
    try:
        data = json.loads(s)
        if isinstance(data, list):
            tokens = [str(x) for x in data]
        elif isinstance(data, str):
            tokens = [data]
        else:
            tokens = []
    except json.JSONDecodeError:
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
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=str(path.parent),
            prefix=path.name + ".", suffix=".tmp",
        ) as tmp:
            tmp_path = Path(tmp.name)
            for w in sorted(words):
                tmp.write(w + "\n")
            tmp.flush()
            os.fchmod(tmp.fileno(), mode)
            os.fsync(tmp.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def backup_file(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    # Exclusive creation prevents repeated runs from overwriting a backup.
    with tempfile.NamedTemporaryFile(
        "wb", dir=str(path.parent), prefix=path.name + f".bak-{ts}-", delete=False,
    ) as tmp:
        backup = Path(tmp.name)
        try:
            with path.open("rb") as source:
                shutil.copyfileobj(source, tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
        except BaseException:
            backup.unlink(missing_ok=True)
            raise
    shutil.copystat(path, backup)
    return backup


def prompt_user(message: str) -> str:
    """Keep interactive responses separate from any piped answer data."""
    if sys.stdin.isatty():
        return input(message)
    with open("/dev/tty", "w", encoding="utf-8") as output:
        output.write(message)
        output.flush()
    with open("/dev/tty", "r", encoding="utf-8") as terminal:
        return terminal.readline().rstrip("\n")


def compute_changes(dict_words: Set[str], answers: Set[str], bad_words: Set[str]):
    """Official answers always take precedence over removal candidates."""
    return answers - dict_words, (dict_words & bad_words) - answers


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
        "--date", "-d",
        help="6-digit date token, e.g. 080925"
    )
    parser.add_argument(
        "--data-dir", "-D",
        default=str(PRUNE_DIR), 
        help="Directory containing answers_*.txt, fakes_*.txt, output_*.txt (default: prune/)" 
    )
    parser.add_argument(
        "--fakes", "-f",
        help="Path to fakes_*.txt"
    )
    parser.add_argument(
        "--answers", "-a",
        help="Path to answers_*.txt"
    )
    parser.add_argument(
        "--output", "-o", 
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
        "-A",
        action="store_true", 
        help="Apply changes (otherwise dry-run)"
    )
    parser.add_argument(
        "--yes", 
        "-y",
        action="store_true", 
        help="Assume yes to prompts when applying"
    )
    parser.add_argument(
        "--no-add",
        "-n",
        action="store_true", 
        help="Do not add missing true words to dictionary"
    )
    parser.add_argument(
        "--no-remove",
        "-k",
        action="store_true",
        help="Do not remove bad/fake words from dictionary"
    )
    parser.add_argument(
        "--conservative",
        "-c",
        action="store_true",
        help="Only remove words that are also NOT in a system dictionary (safer)"
    )
    parser.add_argument(
        "--system-dict",
        "-s",
        default=str(DEFAULT_SYSTEM_DICT),
        help="System dictionary to cross-check (default: /usr/share/dict/words if present)"
    )
    parser.add_argument(
        "--backup",
        "-B",
        action="store_true",
        help="Create a timestamped backup of the dictionary before applying changes"
    )
    parser.add_argument(
        "--show", "-S",
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
        try:
            answers_words = parse_answers_str(args.answers_str)
        except ValueError as exc:
            parser.error(str(exc))
        answers_source = "--answers-str"
    elif args.answers_stdin:
        pasted = sys.stdin.read()
        try:
            answers_words = parse_answers_str(pasted)
        except ValueError as exc:
            parser.error(str(exc))
        answers_source = "--answers-stdin"
    elif args.answers:
        true_path = Path(args.answers).resolve()
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
    if not (args.output and answers_words):
        if args.fakes:
            bad_path = Path(args.fakes).resolve()
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
    missing_words, removal_candidates = compute_changes(dict_words, answers_words, bad_words)

    # Conservative filter
    system_words: Set[str] = set()
    effective_conservative = False
    if args.conservative:
        sys_dict_path = Path(args.system_dict)
        if sys_dict_path.exists():
            system_words = load_system_words(sys_dict_path)
            effective_conservative = True
        else:
            sys.exit(f"Error: system dictionary not found at {sys_dict_path}; cannot use --conservative.")

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
        print("  Bad/Fakes : (none provided; removals disabled or zero)")
    if answers_source:
        print(f"  Answers   : {answers_source}")
    else:
        print("  Answers   : (none provided; additions depend on fakes only)")
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

    # Build the new word set
    new_words = set(dict_words)
    if missing_words:
        new_words |= missing_words
    if to_remove:
        new_words -= to_remove

    if new_words == dict_words:
        print("\nNo changes necessary. Dictionary already up-to-date with provided inputs.")
        return 0

    if not args.yes:
        try:
            proceed = prompt_user("\nApply these changes to the dictionary? [y/N]: ").strip().lower()
        except (OSError, EOFError, KeyboardInterrupt):
            proceed = ""
        if proceed not in {"y", "yes"}:
            print("Aborted. No changes made.")
            return 1

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
