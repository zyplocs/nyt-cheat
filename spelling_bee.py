# Define the allowed letters and the required conditions
allowed_letters = {'p', 'o', 'd', 'n', 'e', 'i', 'w'}
required_letter = 'w'
min_length = 4


# Load words from the system dictionary
def load_words():
    with open('/Users/elijohnson/miscpy/cheats/english-words/words_alpha.txt',
              "r") as f:
        words = {line.strip().lower() for line in f}

        return words


# Filter words based on criteria
def filter_words(word_list, allowed_letters, required_letter, min_length):
    filtered_words = set()
    for word in word_list:
        if (len(word) >= min_length and required_letter in word and set(word).issubset(allowed_letters)):
            filtered_words.add(word)

    return sorted(filtered_words)


# Main script logic
english_words = load_words()
valid_words = filter_words(english_words,
                           allowed_letters,
                           required_letter,
                           min_length)

print(f"{len(valid_words)} Words Found:\n", valid_words)
