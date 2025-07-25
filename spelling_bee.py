#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

# argparse script
def _parse_args() -> argparse.Namespace:
    """Return command-line arguments parsed with `argparse`."""

    default_dict = (
        Path(__file__).parent
        / "english-words/words_alpha.txt"
    )

    p = argparse.ArgumentParser(
        description="Spelling Bee helper: list all valid words given a letter set."
    )
    p.add_argument(
        "letters",
        metavar="LETTERS",
        help="All allowed letters, e.g. 'ahyblti' (7 letters, lowercase or uppercase)",
    )
    p.add_argument(
        "required_letter",
        metavar="CENTER",
        help="The single mandatory (center) letter; must be included in LETTERS.",
    )
    p.add_argument(
        "-m",
        "--min-length",
        type=int,
        default=4,
        help="Minimum word length (default: 4)",
    )
    p.add_argument(
        "-d",
        "--dictionary",
        type=Path,
        default=default_dict,
        help=f"Path to dictionary file (default: {default_dict})",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write results to this file instead of stdout",
    )

    return p.parse_args()


# Core funcs
def load_words(dict_path: Path) -> set[str]:
    """Read the word list from `dict_path` and return a set of lowercase words."""

    try:
        with dict_path.open("r", encoding="utf-8") as f:
            return {line.strip().lower() for line in f if line.strip()}
    except FileNotFoundError as exc:
        sys.exit(f"Dictionary file not found: {dict_path}\n{exc}")


def filter_words(
    word_list: set[str],
    allowed_letters: set[str],
    required_letter: str,
    min_length: int,
) -> list[str]:
    """
    Filter words based on specified criteria.

    ---
    ### Arguments
    `word_list`
        A set of words to filter.
    `allowed_letters`
        A set of allowed letters; each word must only contain these.
    `required_letter`
        A letter that must appear in every word.
    `min_length`
        The minimum length a word must have.

    ---
    ### Returns
    `filtered_words`
        A sorted list of words that meet the criteria.
    """
    filtered_words = set()
    for word in word_list:
        if (
            len(word) >= min_length
            and required_letter in word
            and set(word).issubset(allowed_letters)
        ):
            filtered_words.add(word)

    return sorted(filtered_words)


# Main logic
def main() -> None:  # noqa: D401
    """CLI entry-point."""

    args = _parse_args()

    allowed_letters = set(args.letters.lower())
    required_letter = args.required_letter.lower()

    if required_letter not in allowed_letters:
        sys.exit("Error: required letter must be one of the allowed letters.")

    english_words = load_words(args.dictionary)

    valid_words = filter_words(
        english_words,
        allowed_letters,
        required_letter,
        args.min_length,
    )

    # Emit results
    header = f"{len(valid_words)} words found:"
    word_lines = "\n".join(valid_words)

    if args.output:
        try:
            args.output.write_text(word_lines + "\n", encoding="utf-8")
        except Exception as exc:  # broad but prints nice message instead of crashing
            sys.exit(f"Could not write output file {args.output}: {exc}")

    # Always print to stdout so shell redirection still works
    print(header)
    print(word_lines)


if __name__ == "__main__":
    main()
