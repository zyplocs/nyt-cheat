"""Script to cheat on NYT Wordle."""
from pathlib import Path
from typing import Iterable
import argparse

WORD_LENGTH = 5
LETTERS_IN_SPECIFIC_POSITIONS = {0: "t", 1: "a", 4: "t"}
LETTERS_TO_INCLUDE = set()
LETTERS_NOT_ALLOWED = {"e", "r", "p", "s", "d", "h", "l", "c", "b"}

# argparse script
def parse_args() -> argparse.Namespace:
    """Return command-line arguments parsed with `argparse`."""

    parser = argparse.ArgumentParser(
        description="Filter Wordle candidate words based on constraints."
    )
    parser.add_argument(
        "-l",
        "--length",
        type=int,
        default=5,
        help="Word length (default: 5)",
    )
    parser.add_argument(
        "-p",
        "--position",
        action="append",
        default=[],
        metavar="INDEX:LETTER",
        help=(
            "Fix LETTER at 0-indexed INDEX (e.g., -p 0:t). "
            "May be supplied multiple times."
        ),
    )
    parser.add_argument(
        "-i",
        "--include",
        default="",
        help="Letters that must be present (e.g., 'ar').",
    )
    parser.add_argument(
        "-x",
        "--exclude",
        default="",
        help="Letters that must NOT be present (e.g., 'seb').",
    )
    parser.add_argument(
        "-d",
        "--dictionary",
        type=Path,
        default=Path(__file__).resolve().parent / "english-words" / "words_alpha.txt",
        help="Path to word list file.",
    )
    return parser.parse_args()


# Core funcs
def load_words(filepath: str | Path) -> set[str]:
    """
    Load words from a file, convert each to lowercase, + return them as a set.

    Parameters
    ----------
    - `filepath`: The path to the file containing one word per line.

    Returns
    -------
    - `set[str]`: A set of words from the file.
    """
    with open(filepath) as f:
        words = {line.strip().lower() for line in f}

    return words


def filter_words(
    words: Iterable[str],
    *,
    word_length: int | None = None,
    specific_positions: dict[int, str] | None = None,
    include_letters: Iterable[str] | None = None,
    exclude_letters: Iterable[str] | None = None,
) -> list[str]:
    """
    Filter words based on multiple criteria.

    Parameters
    ----------
    - `words`: An iterable of words to filter.
    - `word_length`: The exact length required for a word.
    - `specific_positions`: A dictionary mapping positions (0-indexed)
                            to letters that must appear at those positions.
    - `include_letters`: A set of letters that must be present in the word.
    - `exclude_letters`: A set of letters that must not be present in the word.

    Returns
    -------
    - `sorted(words)`: A sorted list of words that meet
                                all the criteria.
    """
    include = set(include_letters) if include_letters else set()
    exclude = set(exclude_letters) if exclude_letters else set()
    positions = specific_positions or {}

    return sorted(
        word for word in words
        if (word_length is None or len(word) == word_length)
        and all(word[i] == c for i, c in positions.items() if i < len(word))
        and include.issubset(word)
        and exclude.isdisjoint(word)
    )


# Main logic
def main() -> None:
    """Entry point for CLI usage."""
    args = parse_args()

    # Build position dict from CLI values
    positions: dict[int, str] = {}
    for spec in args.position:
        try:
            idx_str, letter = spec.split(":")
            positions[int(idx_str)] = letter.lower()
        except ValueError as exc:
            raise SystemExit(
                f"Invalid --position value '{spec}'. Expected format INDEX:LETTER."
            ) from exc

    include_letters = set(args.include.lower())
    exclude_letters = set(args.exclude.lower())

    words = load_words(args.dictionary)
    candidates = filter_words(
        words,
        word_length=args.length,
        specific_positions=positions or None,
        include_letters=include_letters,
        exclude_letters=exclude_letters,
    )

    if candidates:
        print("\n".join(candidates))
    else:
        print("No matching words found.")


if __name__ == "__main__":
    main()
