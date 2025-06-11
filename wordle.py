"""Script to cheat on NYT Wordle."""
from pathlib import Path
from typing import Iterable

# Search conditions
WORD_LENGTH = 5
LETTERS_IN_SPECIFIC_POSITIONS = {1: "n", 3: "o"}
LETTERS_TO_INCLUDE = {"i"}
LETTERS_NOT_ALLOWED = {"e", "r", "t", "u", "a", "s", "l", "c"}

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

def main() -> None:
    """Create the main execution flow."""
    dataset_path = Path(__file__).resolve().parent / "english-words" / "words_alpha.txt"
    DICTIONARY_WORDS = load_words(dataset_path)
    candidates = filter_words(
        DICTIONARY_WORDS,
        word_length=WORD_LENGTH,
        specific_positions=LETTERS_IN_SPECIFIC_POSITIONS,
        include_letters=LETTERS_TO_INCLUDE,
        exclude_letters=LETTERS_NOT_ALLOWED,
    )
    print("\n".join(candidates))


if __name__ == "__main__":
    main()
