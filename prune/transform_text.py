"""Chop hefty blocks of answers into a JSON-style array."""

import json
import re
import sys
from dataclasses import dataclass

# If working locally, feel free to paste the text block in the constant below
#
# Alternately, skip editing this file and pipe clipboard text:
#   pbpaste | python3 prune/transform_text.py
PASTED_TEXT = """
"""


@dataclass(frozen=True)
class AnswerTable:
    words: tuple[str, ...]
    pangrams: frozenset[str]


def parse_answer_table(text: str) -> AnswerTable:
    """Read words with optional lengths and pangram labels; reject invalid rows."""
    text = text.strip()
    if len(text) >= 2 and (text[0], text[-1]) in {
        ('"', '"'), ("'", "'"), ('“', '”'),
    }:
        text = text[1:-1].strip()
    words = []
    pangrams = set()
    seen = set()

    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(
            r"\s*([A-Za-z]{4,})(?:\s+([0-9]+))?(?:\s+(pangram))?\s*",
            line, re.IGNORECASE | re.ASCII,
        )
        if not match:
            raise ValueError(f"Line {number}: expected a word, optional length, and optional 'pangram' label.")
        word, length, marker = match.groups()
        word = word.lower()
        if length is not None and int(length) != len(word):
            raise ValueError(f"Line {number}: {word.upper()} has {len(word)} letters, not {length}.")
        if word in seen:
            raise ValueError(f"Line {number}: duplicate answer {word.upper()}.")
        seen.add(word)
        words.append(word)
        if marker:
            pangrams.add(word)
    if not words:
        raise ValueError("No answers found. Copy the complete answer table first.")
    return AnswerTable(tuple(words), frozenset(pangrams))


def parse_word_block(text: str) -> list[str]:
    """Extract validated lowercase words and move pangrams to the front."""
    table = parse_answer_table(text)
    return ([w for w in table.words if w in table.pangrams]
            + [w for w in table.words if w not in table.pangrams])


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
    try:
        words = parse_word_block(get_input_text())
    except ValueError as exc:
        raise SystemExit(f"Error: {exc}") from exc
    print(json.dumps(words))


if __name__ == "__main__":
    main()
