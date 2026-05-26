"""Fetch official NYT Spelling Bee answers into prune/data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from extractor import (
    SPELLING_BEE_URL,
    SpellingBeeDataError,
    SpellingBeeFetchError,
    find_puzzle,
    list_puzzles,
    load_game_data,
    write_answers_file,
)


DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Fetch official NYT Spelling Bee answers from embedded page data."
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
        help=f"Directory for answers_*.txt files. Default: {DEFAULT_DATA_DIR}",
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
        "--list",
        action="store_true",
        help="List accessible puzzle dates and exit.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print selected answers to stdout instead of writing a file.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing answers file.",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry-point."""

    args = parse_args(argv)
    game_data = load_game_data(html_path=args.html, url=args.url)

    if args.list:
        print_puzzle_table(list_puzzles(game_data))
        return 0

    puzzle = find_puzzle(game_data, args.selector)

    if args.stdout:
        print("\n".join(puzzle.answers))
        return 0

    output_path = write_answers_file(
        puzzle,
        args.data_dir,
        overwrite=args.force,
    )

    print(f"Date     : {puzzle.display_date} ({puzzle.print_date})")
    print(f"Token    : {puzzle.date_token}")
    print(f"Center   : {puzzle.center_letter}")
    print(f"Letters  : {puzzle.letters_string}")
    print(f"Pangrams : {', '.join(puzzle.pangrams)}")
    print(f"Answers  : {len(puzzle.answers)}")
    print(f"Wrote    : {output_path}")

    return 0


def print_puzzle_table(puzzles) -> None:
    """Print a compact table of accessible puzzles."""

    print(f"{'Date':<10} {'Day':<9} {'Center':<6} {'Letters':<7} {'Answers':>7} Pangrams")

    for puzzle in puzzles:
        pangrams = ", ".join(puzzle.pangrams)
        print(
            f"{puzzle.print_date:<10} "
            f"{puzzle.display_weekday:<9} "
            f"{puzzle.center_letter:<6} "
            f"{puzzle.letters_string:<7} "
            f"{len(puzzle.answers):>7} "
            f"{pangrams}"
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
