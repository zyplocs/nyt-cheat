# NYT Games Cheats

This repository contains small Python helpers for finding candidate words for NYT Wordle and Spelling Bee.

The scripts use the word list at `english-words/words_alpha.txt`. The terminal interfaces are `curses`-based modules.

## Requirements

Use Python 3.10+.

If the word list is missing after cloning the repository, initialize the submodule:

```sh
git submodule update --init --recursive
```

## Wordle

Run the command-line Wordle helper with constraints for word length, fixed positions, included letters, and excluded letters.

```sh
python wordle.py --length 5 --position 0:t --include ar --exclude seb
```

Run the terminal interface with:

```sh
python wordle_tui.py
```

## Spelling Bee

Run the command-line Spelling Bee helper with the allowed letters and the required center letter.

```sh
python spelling_bee.py ahyblti y
```

Run the terminal interface with:

```sh
python spelling_bee_tui.py
```

## Notes

These scripts are generally local tools, with a few exceptions.
