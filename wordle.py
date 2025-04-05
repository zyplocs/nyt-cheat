# Define search conditions
word_length = 5
letters_in_specific_positions = {1: "r", 2: "i", 3: "l", 4: "l"}
letters_to_include = set()
letters_not_allowed = {"e", "t", "o", "a", "s", "d", "f", "g", "h", "c", "n"}


# Load words from system dictionary
def load_words(filepath: str) -> set[str]:
    """
    Load words from a file, convert each to lowercase, + return them as a set.

    Args:
        filepath: The path to the file containing one word per line.

    Returns:
        A set of words from the file.
    """
    with open(filepath, "r") as f:
        words = {line.strip().lower() for line in f}

    return words


# Function to filter words based on given conditions
def filter_words(
    word_list: set[str],
    word_length: int | None = None,
    specific_positions: dict[int, str] | None = None,
    include_letters: set[str] | None = None,
    exclude_letters: set[str] | None = None,
) -> list[str]:
    """
    Filter words based on multiple criteria.

    Args:
        word_list: A set of words to filter.
        word_length: The exact length required for a word.
        specific_positions: A dictionary mapping positions (0-indexed) to letters that must appear at those positions.
        include_letters: A set of letters that must be present in the word.
        exclude_letters: A set of letters that must not be present in the word.

    Returns:
        A sorted list of words that meet all the criteria.
    """
    filtered_words = set()

    for word in word_list:
        if word_length is not None and len(word) != word_length:
            continue

        # Create a set of word letters for repeated use
        word_set = set(word)

        # Check if letters are in specific positions, if specified
        if specific_positions:
            if any(word[pos] != letter for pos, letter in specific_positions.items()):
                continue

        # Check if it contains required letters, if specified
        if include_letters and not include_letters.issubset(word_set):
            continue

        if exclude_letters and any(letter in word_set for letter in exclude_letters):
            continue

        filtered_words.add(word)

    return sorted(filtered_words)


# Main script logic
def main():
    filepath = "/Users/elij/zypy/cheats/english-words/words_alpha.txt"
    english_words = load_words(filepath)
    valid_words = filter_words(
        english_words,
        word_length=word_length,
        specific_positions=letters_in_specific_positions,
        include_letters=letters_to_include,
        exclude_letters=letters_not_allowed,
    )

    print(valid_words)


if __name__ == "__main__":
    main()
