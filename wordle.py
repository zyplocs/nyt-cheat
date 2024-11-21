# Define search conditions
word_length = 5
letters_in_specific_positions = {1: 'e', 3: 'r'}
letters_to_include = set()
letters_not_allowed = {'a', 's', 't', 'o', 'n'}


# Load words from system dictionary
def load_words(filepath):
    with open(filepath, "r") as f:
        words = {line.strip().lower() for line in f}

    return words


# Function to filter words based on given conditions
def filter_words(word_list,
                 word_length=None,
                 specific_positions=None,
                 include_letters=None,
                 exclude_letters=None):
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
filepath = '/Users/elijohnson/miscpy/cheats/english-words/words_alpha.txt'
english_words = load_words(filepath)
valid_words = filter_words(
    english_words,
    word_length=word_length,
    specific_positions=letters_in_specific_positions,
    include_letters=letters_to_include,
    exclude_letters=letters_not_allowed
)

print(valid_words)
