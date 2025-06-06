# Define the allowed letters and the required conditions
allowed_letters = {"d", "i", "l", "t", "m", "a", "n"}
required_letter = "l"
min_length = 4


def load_words() -> set[str]:
    """
    Load words from the system dictionary file.

    Returns
    -------
    words: A set of lowercase words read from the file.
    """
    with open(
        "/Users/elijohnson/miscpy/cheats/english-words/words_alpha.txt", "r"
    ) as f:
        words = {line.strip().lower() for line in f}

        return words


def filter_words(
    word_list: set[str],
    allowed_letters: set[str],
    required_letter: str,
    min_length: int,
    ) -> list[str]:
    """
    Filter words based on specified criteria.

    Arguments
    ---------
    word_list: A set of words to filter.
    allowed_letters: A set of allowed letters; each word must only contain these.
    required_letter: A letter that must appear in every word.
    min_length: The minimum length a word must have.

    Returns
    -------
    filtered_words: A sorted list of words that meet the criteria.
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


# Main script logic
def main():
    english_words = load_words()
    valid_words = filter_words(
        english_words, allowed_letters, required_letter, min_length
    )

    print(f"{len(valid_words)} Words Found:\n", valid_words)


if __name__ == "__main__":
    main()
