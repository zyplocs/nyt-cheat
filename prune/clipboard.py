"""Preview and apply a complete Spelling Bee answer key from the macOS clipboard."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from spelling_bee import filter_words
from prune import pruner
from prune.transform_text import AnswerTable, parse_answer_table


def read_clipboard() -> str:
    try:
        result = subprocess.run(
            ["/usr/bin/pbpaste"], capture_output=True, text=True,
            encoding="utf-8", check=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise ValueError("Could not read the macOS clipboard. Copy the answer table and retry.") from exc
    return result.stdout


def puzzle_letters(table: AnswerTable) -> tuple[set[str], set[str]]:
    if not table.pangrams:
        raise ValueError("Include the 'pangram' label in the copied answer table so the puzzle letters can be verified.")
    letters = set(next(iter(table.pangrams)))
    if len(letters) != 7:
        raise ValueError("A marked pangram must contain exactly seven distinct letters.")
    if any(set(word) != letters for word in table.pangrams):
        raise ValueError("The marked pangrams do not use the same seven letters.")
    if any(not set(word) <= letters for word in table.words):
        raise ValueError("Some answers contain letters outside the marked pangram. Check that the key is for one puzzle.")
    centers = set.intersection(*(set(word) for word in table.words))
    if not centers:
        raise ValueError("There is no letter shared by every answer. Check that the key is for one puzzle.")
    return letters, centers


def choose_center(centers: set[str], supplied: str | None) -> str:
    if supplied is not None:
        center = supplied.strip().lower()
        if center not in centers:
            raise ValueError("The center must be one letter present in every answer: " + ", ".join(sorted(centers)).upper())
        return center
    if len(centers) == 1:
        return next(iter(centers))
    choices = ", ".join(sorted(centers)).upper()
    while True:
        center = pruner.prompt_user(f"Possible center letters: {choices}. Enter the puzzle's center (blank cancels): ").strip().lower()
        if not center:
            raise ValueError("No center selected. No changes made.")
        if center in centers:
            return center
        print(f"Choose one letter from {choices}.")


def run(args: argparse.Namespace) -> int:
    table = parse_answer_table(read_clipboard())
    letters, centers = puzzle_letters(table)
    center = choose_center(centers, args.center)
    path = args.dictionary.expanduser().resolve()
    original = path.read_bytes()
    dictionary = {line.strip().lower() for line in original.decode("utf-8").splitlines() if line.strip()}
    answers = set(table.words)
    candidates = set(filter_words(dictionary, letters, center, 4))
    additions, removals = pruner.compute_changes(dictionary, answers, candidates - answers)
    if args.conservative:
        # Reading a missing or unreadable dictionary fails before any changes.
        system_words = pruner.read_words(args.system_dict.expanduser())
        removals -= system_words

    print(f"Dictionary: {path}")
    print(f"Letters: {''.join(sorted(letters)).upper()} · Center: {center.upper()}")
    print(f"{len(answers)} answers · {len(candidates)} dictionary candidates")
    pruner.preview("Add", additions, len(additions))
    pruner.preview("Remove", removals, len(removals))
    if not additions and not removals:
        print("\nNo changes needed under the selected settings." if args.conservative
              else "\nDictionary already matches this answer key.")
        return 0
    if args.dry_run:
        print("\nPreview only. No changes written.")
        return 0

    print("\nRemovals assume this is the complete answer key for this puzzle.")
    response = pruner.prompt_user("Apply these changes? [y/N]: ").strip().lower()
    if response not in {"y", "yes"}:
        print("Cancelled. No changes made.")
        return 0
    if path.read_bytes() != original:
        raise ValueError("The dictionary changed after the preview. Rerun to review the new changes.")
    backup = pruner.backup_file(path)
    print(f"Backup: {backup}")
    if backup.read_bytes() != original or path.read_bytes() != original:
        raise ValueError("The dictionary changed during backup. Rerun to review the new changes.")
    pruner.write_words_atomic(path, (dictionary | additions) - removals)
    print(f"Applied: added {len(additions)}, removed {len(removals)}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dict", dest="dictionary", type=Path, default=pruner.DEFAULT_DICT,
                        help="Dictionary to update (default: english-words/words_alpha.txt)")
    parser.add_argument("--center", help="Center letter, if it cannot be inferred uniquely")
    parser.add_argument("--dry-run", action="store_true", help="Preview without offering to apply changes")
    parser.add_argument("--conservative", action="store_true", help="Preserve candidates found in the system dictionary")
    parser.add_argument("--system-dict", type=Path, default=pruner.DEFAULT_SYSTEM_DICT,
                        help="Dictionary used by --conservative")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (OSError, ValueError, EOFError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
