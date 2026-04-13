"""Chop hefty blocks of answers into a JSON-style array."""

import json
import sys

# Paste a block of text between the triple quotes, then run:
#   python3 prune/transform_text.py
#
# Or skip editing this file and pipe clipboard text instead:
#   pbpaste | python3 prune/transform_text.py
PASTED_TEXT = """
"""


def parse_word_block(text: str) -> list[str]:
    """Extract lowercase words and move pangrams to the front."""
    pangrams = []
    others = []

    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue

        word = parts[0].lower()

        if "pangram" in parts[1:]:
            pangrams.append(word)
        else:
            others.append(word)

    return pangrams + others


def get_input_text() -> str:
    """Prefer piped stdin; otherwise use the editable paste block above."""
    if not sys.stdin.isatty():
        stdin_text = sys.stdin.read().strip()
        if stdin_text:
            return stdin_text

    pasted_text = PASTED_TEXT.strip()
    if pasted_text:
        return pasted_text

    raise SystemExit(
        "No input found. Paste text into PASTED_TEXT or pipe it in via stdin."
    )


def main() -> None:
    """CLI entry-point."""
    words = parse_word_block(get_input_text())
    print(json.dumps(words))


if __name__ == "__main__":
    main()
