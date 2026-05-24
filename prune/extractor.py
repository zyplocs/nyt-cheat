"""Utilities for extracting NYT Spelling Bee data from page HTML."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SPELLING_BEE_URL = "https://www.nytimes.com/puzzles/spelling-bee"


class SpellingBeeFetchError(RuntimeError):
    """Raised when fetching the NYT Spelling Bee page fails."""

class SpellingBeeDataError(ValueError):
    """Raised when the page does not contain parseable Spelling Bee data."""


@dataclass(frozen=True, slots=True)
class Puzzle:
    """A single Spelling Bee puzzle extracted from NYT page data."""

    print_date: str
    display_date: str
    display_weekday: str
    center_letter: str
    outer_letters: list[str]
    valid_letters: list[str]
    pangrams: list[str]
    answers: list[str]
    puzzle_id: int | None = None
    editor: str | None = None

    @property
    def date_token(self) -> str:
        """Return the MMDDYY token used by prune/data filenames."""
        parsed_date = date.fromisoformat(self.print_date)
        return parsed_date.strftime("%m%d%y")

    @property
    def letters_string(self) -> str:
        """Return the seven valid letters as one string."""
        return "".join(self.valid_letters)


def fetch_html(url: str = SPELLING_BEE_URL, timeout: int = 20) -> str:
    """Fetch the Spelling Bee page HTML."""

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            encoding = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(encoding)
    except HTTPError as exc:
        raise SpellingBeeFetchError(
            f"NYT request failed with HTTP {exc.code}: {exc.reason}"
        ) from exc
    except URLError as exc:
        raise SpellingBeeFetchError(f"Could not reach NYT: {exc.reason}") from exc
    except TimeoutError as exc:
        raise SpellingBeeFetchError("NYT request timed out.") from exc


def load_game_data(
    *,
    html_path: Path | None = None,
    url: str = SPELLING_BEE_URL,
) -> dict[str, Any]:
    """Load game data from either a saved HTML file or the live NYT page."""

    html = (
        html_path.read_text(encoding="utf-8")
        if html_path is not None
        else fetch_html(url)
    )

    return extract_game_data(html)


def extract_game_data(html: str) -> dict[str, Any]:
    """Extract and parse the object assigned to window.gameData."""

    marker = "window.gameData"
    marker_index = html.find(marker)

    if marker_index == -1:
        raise SpellingBeeDataError("Could not find window.gameData in the HTML.")

    script_end = html.find("</script>", marker_index)
    search_end = script_end if script_end != -1 else len(html)

    equals_index = html.find("=", marker_index, search_end)

    if equals_index == -1:
        raise SpellingBeeDataError("Found window.gameData, but not its assignment.")

    object_start = html.find("{", equals_index, search_end)

    if object_start == -1:
        raise SpellingBeeDataError("Found window.gameData, but not its object.")

    object_end = find_matching_json_object_end(html, object_start)
    raw_object = html[object_start : object_end + 1]

    try:
        parsed = json.loads(raw_object)
    except json.JSONDecodeError as exc:
        raise SpellingBeeDataError(
            "window.gameData was found, but it was not valid JSON."
        ) from exc

    if not isinstance(parsed, dict):
        raise SpellingBeeDataError("window.gameData did not parse into an object.")

    return parsed


def find_matching_json_object_end(text: str, start_index: int) -> int:
    """Return the index of the closing brace matching text[start_index]."""

    if text[start_index] != "{":
        raise ValueError("start_index must point to an opening brace.")

    depth = 0
    in_string = False
    escaped = False

    for index in range(start_index, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False

            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1

            if depth == 0:
                return index

    raise SpellingBeeDataError("Could not find the end of window.gameData.")


def puzzle_from_dict(data: dict[str, Any]) -> Puzzle:
    """Convert one raw NYT puzzle dictionary into a Puzzle object."""

    required_keys = {
        "printDate",
        "displayDate",
        "displayWeekday",
        "centerLetter",
        "outerLetters",
        "validLetters",
        "pangrams",
        "answers",
    }
    missing_keys = sorted(required_keys - data.keys())

    if missing_keys:
        joined = ", ".join(missing_keys)
        raise SpellingBeeDataError(f"Puzzle is missing required keys: {joined}")

    raw_id = data.get("id")
    puzzle_id = int(raw_id) if raw_id is not None else None

    return Puzzle(
        print_date=str(data["printDate"]),
        display_date=str(data["displayDate"]),
        display_weekday=str(data["displayWeekday"]),
        center_letter=str(data["centerLetter"]).lower(),
        outer_letters=_string_list(data["outerLetters"]),
        valid_letters=_string_list(data["validLetters"]),
        pangrams=_string_list(data["pangrams"]),
        answers=_string_list(data["answers"]),
        puzzle_id=puzzle_id,
        editor=str(data["editor"]) if data.get("editor") is not None else None,
    )


def _string_list(value: Any) -> list[str]:
    """Return a lowercase string list from a JSON list value."""

    if not isinstance(value, list):
        raise SpellingBeeDataError(f"Expected list value, got {type(value).__name__}.")

    return [str(item).lower() for item in value]


def iter_puzzle_dicts(value: Any) -> list[dict[str, Any]]:
    """Find all puzzle-shaped dictionaries inside a nested JSON object."""

    puzzles: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if {"printDate", "centerLetter", "validLetters", "answers"} <= node.keys():
                puzzles.append(node)

            for child in node.values():
                visit(child)

        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(value)
    return puzzles


def list_puzzles(game_data: dict[str, Any]) -> list[Puzzle]:
    """Return all accessible puzzles, deduped by printDate."""

    puzzles: list[Puzzle] = []
    seen_dates: set[str] = set()

    for raw_puzzle in iter_puzzle_dicts(game_data):
        puzzle = puzzle_from_dict(raw_puzzle)

        if puzzle.print_date in seen_dates:
            continue

        puzzles.append(puzzle)
        seen_dates.add(puzzle.print_date)

    return sorted(puzzles, key=lambda puzzle: puzzle.print_date)


def find_puzzle(game_data: dict[str, Any], selector: str) -> Puzzle:
    """Find a puzzle by 'today', 'yesterday', MMDDYY, or YYYY-MM-DD."""

    normalized = selector.strip().lower()

    if normalized in {"today", "yesterday"}:
        try:
            return puzzle_from_dict(game_data[normalized])
        except KeyError as exc:
            raise SpellingBeeDataError(f"No {normalized!r} puzzle found.") from exc

    target_date = normalize_date_selector(normalized)

    for puzzle in list_puzzles(game_data):
        if puzzle.print_date == target_date:
            return puzzle

    available_dates = ", ".join(puzzle.print_date for puzzle in list_puzzles(game_data))

    raise SpellingBeeDataError(
        f"No accessible puzzle found for {target_date}. "
        f"Available dates: {available_dates}"
    )


def normalize_date_selector(selector: str) -> str:
    """Normalize MMDDYY or YYYY-MM-DD into YYYY-MM-DD."""

    if len(selector) == 6 and selector.isdigit():
        return datetime.strptime(selector, "%m%d%y").date().isoformat()

    try:
        return date.fromisoformat(selector).isoformat()
    except ValueError as exc:
        raise SpellingBeeDataError(
            "Puzzle selector must be 'today', 'yesterday', MMDDYY, or YYYY-MM-DD."
        ) from exc


def write_answers_file(
    puzzle: Puzzle,
    data_dir: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write official answers to answers_MMDDYY.txt."""

    return write_word_file(
        data_dir / f"answers_{puzzle.date_token}.txt",
        puzzle.answers,
        overwrite=overwrite,
        preserve_order=True,
    )


def write_word_file(
    path: Path,
    words: Iterable[str],
    *,
    overwrite: bool = False,
    preserve_order: bool = False,
) -> Path:
    """Write one lowercase word per line, avoiding accidental overwrites."""

    normalized_words = _normalize_words(words, preserve_order=preserve_order)
    content = "\n".join(normalized_words)

    if content:
        content += "\n"

    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        existing = path.read_text(encoding="utf-8")

        if existing == content:
            return path

        if not overwrite:
            raise FileExistsError(f"{path} already exists. Use --force to overwrite it.")

    path.write_text(content, encoding="utf-8")
    return path


def _normalize_words(words: Iterable[str], *, preserve_order: bool) -> list[str]:
    """Normalize words while either preserving order or sorting."""

    if preserve_order:
        output: list[str] = []
        seen: set[str] = set()

        for word in words:
            normalized = str(word).strip().lower()

            if normalized and normalized not in seen:
                output.append(normalized)
                seen.add(normalized)

        return output

    return sorted({str(word).strip().lower() for word in words if str(word).strip()})
