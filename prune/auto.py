"""Fetch a Spelling Bee puzzle, generate candidates, and prepare pruning files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

import spelling_bee
from prune import pruner
from prune.extractor import (
    SPELLING_BEE_URL,
    Puzzle,
    SpellingBeeDataError,
    SpellingBeeFetchError,
    find_puzzle,
    load_game_data,
    write_answers_file,
    write_word_file,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PRUNE_DIR = Path(__file__).resolve().parent

DEFAULT_DATA_DIR = PRUNE_DIR / "data"
DEFAULT_DICT = REPO_ROOT / "english-words" / "words_alpha.txt"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Fetch official NYT Spelling Bee answers, generate local candidates, "
            "compute fake words, and optionally run the dictionary pruner."
        )
    )

    parser.add_argument(
        "selector",
        nargs="?",
        default="today",
        help="'today', 'yesterday', MMDDYY, or YYYY-MM-DD. Default: today.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Directory for generated files. Default: {DEFAULT_DATA_DIR}",
    )
    parser.add_argument(
        "--dict",
        dest="dictionary",
        type=Path,
        default=DEFAULT_DICT,
        help=f"Dictionary path. Default: {DEFAULT_DICT}",
    )
    parser.add_argument(
        "--html",
        type=Path,
        help="Read from a saved HTML response instead of fetching the web page.",
    )
    parser.add_argument(
        "--url",
        default=SPELLING_BEE_URL,
        help=f"Spelling Bee URL to fetch. Default: {SPELLING_BEE_URL}",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite generated answers/output/fakes files if their contents differ.",
    )
    parser.add_argument(
        "--show",
        type=int,
        default=25,
        help="Number of fake/missing words to preview. Default: 25.",
    )

    parser.add_argument(
        "--no-pruner",
        action="store_true",
        help="Only generate files and comparison summary; do not invoke pruner.py.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Pass --apply to pruner.py and modify the dictionary.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Pass --yes to pruner.py when applying changes.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a dictionary backup when using --apply.",
    )
    parser.add_argument(
        "--conservative",
        action="store_true",
        help="Pass --conservative to pruner.py.",
    )
    parser.add_argument(
        "--no-add",
        action="store_true",
        help="Pass --no-add to pruner.py.",
    )
    parser.add_argument(
        "--no-remove",
        action="store_true",
        help="Pass --no-remove to pruner.py.",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry-point."""

    args = parse_args(argv)

    if args.apply and args.no_pruner:
        raise ValueError("--apply requires pruner.py; remove --no-pruner.")

    data_dir = args.data_dir.resolve()
    dictionary = args.dictionary.resolve()

    game_data = load_game_data(html_path=args.html, url=args.url)
    puzzle = find_puzzle(game_data, args.selector)

    candidates = generate_candidates(puzzle, dictionary)
    fake_words = set(candidates) - set(puzzle.answers)
    missing_words = set(puzzle.answers) - set(candidates)

    answers_path = write_answers_file(
        puzzle,
        data_dir,
        overwrite=args.force,
    )
    output_path = write_word_file(
        data_dir / f"output_{puzzle.date_token}.txt",
        candidates,
        overwrite=args.force,
    )
    fakes_path = write_word_file(
        data_dir / f"fakes_{puzzle.date_token}.txt",
        fake_words,
        overwrite=args.force,
    )

    print_summary(
        puzzle=puzzle,
        dictionary=dictionary,
        answers_path=answers_path,
        output_path=output_path,
        fakes_path=fakes_path,
        candidates=candidates,
        fake_words=fake_words,
        missing_words=missing_words,
        show=args.show,
    )

    if args.no_pruner:
        print_next_pruner_command(puzzle, data_dir, dictionary)
        return 0

    print("\nPruner:")
    return run_pruner(
        puzzle=puzzle,
        data_dir=data_dir,
        dictionary=dictionary,
        show=args.show,
        apply=args.apply,
        yes=args.yes,
        backup=not args.no_backup,
        conservative=args.conservative,
        no_add=args.no_add,
        no_remove=args.no_remove,
    )


def generate_candidates(puzzle: Puzzle, dictionary: Path) -> list[str]:
    """Generate local dictionary candidates for a puzzle."""

    dictionary_words = spelling_bee.load_words(dictionary)

    return spelling_bee.filter_words(
        word_list=dictionary_words,
        allowed_letters=set(puzzle.valid_letters),
        required_letter=puzzle.center_letter,
        min_length=4,
    )


def run_pruner(
    *,
    puzzle: Puzzle,
    data_dir: Path,
    dictionary: Path,
    show: int,
    apply: bool,
    yes: bool,
    backup: bool,
    conservative: bool,
    no_add: bool,
    no_remove: bool,
) -> int:
    """Run prune/pruner.py with generated files."""

    argv = [
        "--date",
        puzzle.date_token,
        "--data-dir",
        str(data_dir),
        "--dict",
        str(dictionary),
        "--show",
        str(show),
    ]

    if conservative:
        argv.append("--conservative")

    if no_add:
        argv.append("--no-add")

    if no_remove:
        argv.append("--no-remove")

    if apply:
        argv.append("--apply")

        if yes:
            argv.append("--yes")

        if backup:
            argv.append("--backup")

    return pruner.main(argv)


def print_summary(
    *,
    puzzle: Puzzle,
    dictionary: Path,
    answers_path: Path,
    output_path: Path,
    fakes_path: Path,
    candidates: list[str],
    fake_words: set[str],
    missing_words: set[str],
    show: int,
) -> None:
    """Print a human-readable summary."""

    print("Puzzle:")
    print(f"  Date       : {puzzle.display_date} ({puzzle.print_date})")
    print(f"  Token      : {puzzle.date_token}")
    print(f"  Center     : {puzzle.center_letter}")
    print(f"  Letters    : {puzzle.letters_string}")
    print(f"  Pangrams   : {', '.join(puzzle.pangrams)}")
    print(f"  Official   : {len(puzzle.answers)} answers")
    print(f"  Generated  : {len(candidates)} candidates")
    print(f"  Fake words : {len(fake_words)}")
    print(f"  Missing    : {len(missing_words)}")

    print("\nFiles:")
    print(f"  Dictionary : {dictionary}")
    print(f"  Answers    : {answers_path}")
    print(f"  Output     : {output_path}")
    print(f"  Fakes      : {fakes_path}")

    print_preview("Fake words", fake_words, show)
    print_preview("Missing official words", missing_words, show)


def print_preview(title: str, words: Iterable[str], limit: int) -> None:
    """Print a bounded preview of words."""

    sorted_words = sorted(words)

    print(f"\n{title}: {len(sorted_words)}")

    for word in sorted_words[:limit]:
        print(f"  - {word}")

    remaining = len(sorted_words) - limit

    if remaining > 0:
        print(f"  ... and {remaining} more")


def print_next_pruner_command(puzzle: Puzzle, data_dir: Path, dictionary: Path) -> None:
    """Print the next command when --no-pruner is used."""

    print("\nNext dry-run command:")
    print(
        "  python prune/pruner.py "
        f"--date {puzzle.date_token} "
        f"--data-dir {data_dir} "
        f"--dict {dictionary}"
    )


def cli() -> int:
    """Run main with user-friendly error messages."""

    try:
        return main()
    except (
        FileExistsError,
        OSError,
        SpellingBeeDataError,
        SpellingBeeFetchError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
