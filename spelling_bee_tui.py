#!/usr/bin/env python3

# spelling_bee_curses.py
"""TUI helper for NYT Spelling Bee

Python 3.10+ is required because the key-dispatch loop relies on
`match … case` (structural pattern matching).

Usage
-----
$ python spelling_bee_curses.py

Inside the UI
-------------
• Tab         cycle between the three editable fields.
• Space       enter/exit text editing mode for the active field
• ↑ / k       scroll results up (when not in edit mode)
• ↓ / j       scroll results down (when not in edit mode)
• Enter       run the filter with current params
• Esc         exit text editing mode / quit program
• q           quit program (when not in edit mode)
"""
from __future__ import annotations

import curses
from pathlib import Path


ALLOWED_LETTERS_DEFAULT: set[str] = {"d", "i", "l", "t", "m", "a", "n"}
REQUIRED_LETTER_DEFAULT: str = "l"
MIN_LENGTH_DEFAULT: int = 4

# Locate words list relative to this script
WORD_FILE = Path(__file__).resolve().parent / "english-words" / "words_alpha.txt"


def load_words(path: Path = WORD_FILE) -> set[str]:
    """Return a set of lowercase words read from `path`."""
    with open(path, "r", encoding="utf-8") as fp:
        return {line.strip().lower() for line in fp}


def filter_words(
    words: set[str],
    allowed: set[str],
    required: str,
    min_len: int,
) -> list[str]:
    """Return lexicographically-sorted list matching Spelling Bee rules."""
    return sorted(
        w
        for w in words
        if len(w) >= min_len and required in w and set(w) <= allowed
    )

def is_pangram(word: str, allowed: set[str]) -> bool:
    return set(word) == allowed

WORDS: set[str] = load_words()

# Begin curses UI
HELP_BAR = (
    "Letters ({letters})  Required ({required})  MinLen ({min_len})  ~  [Tab] cycle  [Space] edit  [Enter] run  [q] quit"
)

class PAIR:
    ERROR  = 1
    HELP   = 2
    FOCUS  = 3
    HEADER = 4

def init_colors() -> dict[str, int]:
    palette: dict[str, int] = {
        "normal":    curses.A_NORMAL,
        "bold":      curses.A_BOLD,
        "underline": curses.A_UNDERLINE,
        "reverse":   curses.A_REVERSE,

        "error":     curses.A_BOLD,
        "help":      curses.A_BOLD,
        "focus":     curses.A_UNDERLINE,
        "editing":   curses.A_REVERSE | curses.A_BOLD,
        "header":    curses.A_BOLD,
    }
    if not curses.has_colors():
        return palette
    try:
        curses.start_color()
        bg = -1
        try:
            curses.use_default_colors()
        except curses.error:
            bg = curses.COLOR_BLACK

        curses.init_pair(PAIR.ERROR,  curses.COLOR_RED,     bg)
        curses.init_pair(PAIR.HELP,   curses.COLOR_CYAN,    bg)
        curses.init_pair(PAIR.FOCUS,  curses.COLOR_MAGENTA, bg)
        curses.init_pair(PAIR.HEADER, curses.COLOR_GREEN,   bg)

        palette["error"]   |= curses.color_pair(PAIR.ERROR)
        palette["help"]    |= curses.color_pair(PAIR.HELP)
        palette["focus"]   |= curses.color_pair(PAIR.FOCUS)
        palette["editing"] |= curses.color_pair(PAIR.FOCUS)
        palette["header"]  |= curses.color_pair(PAIR.HEADER)
    except curses.error:
        pass
    return palette

# Key codes grouped in a dotted namespace for pattern matching
class KEYS:
    Q = ord("q")
    K = ord("k")
    J = ord("j")


def prompt_initial_params(stdscr: "curses._CursesWindow") -> tuple[str, str, int]:  # type: ignore[name-defined]
    """Interactive startup form asking the user for initial parameters.

    Hitting *Enter* on an empty line keeps the default value.
    Returns `(letters, required_letter, min_length)`.
    """
    curses.echo()
    stdscr.clear()
    stdscr.addstr(0, 0, "NYT Spelling-Bee Cheater ~ press Enter to accept default values", curses.A_BOLD)

    stdscr.addstr(2, 0, f"Letters (default {''.join(ALLOWED_LETTERS_DEFAULT)}): ")
    letters_in = stdscr.getstr().decode().strip().lower()

    stdscr.addstr(3, 0, f"Required letter (default {REQUIRED_LETTER_DEFAULT}): ")
    required_in = stdscr.getstr().decode().strip().lower()

    stdscr.addstr(4, 0, f"Minimum word length (default {MIN_LENGTH_DEFAULT}): ")
    min_len_in = stdscr.getstr().decode().strip()

    curses.noecho()
    stdscr.clear()

    letters = letters_in or "".join(ALLOWED_LETTERS_DEFAULT)
    required = (required_in or REQUIRED_LETTER_DEFAULT)[:1]
    try:
        min_len = int(min_len_in) if min_len_in else MIN_LENGTH_DEFAULT
    except ValueError:
        # Non-numeric min length: treat as 0
        min_len = MIN_LENGTH_DEFAULT

    return letters, required, min_len


class Field:
    """Tiny helper to store text-input field metadata."""

    def __init__(self, label: str, x: int, width: int, value: str = "", field_type: str = "text", palette: dict[str, int] | None = None) -> None:
        self.label = label
        self.x = x  # column position on the screen
        self.width = width  # max chars displayed (incl. space for cursor)
        self.value = value
        self.field_type = field_type  # "letters", "required", or "minlen"
        self.palette = palette or {"normal": curses.A_NORMAL, "focus": curses.A_UNDERLINE, "editing": curses.A_REVERSE | curses.A_BOLD}

    def render(self, win: "curses._CursesWindow", y: int, focused: bool, editing: bool = False) -> None:
        """Render the field with appropriate highlighting."""
        try:
            attr = (
                self.palette["editing"] if editing
                else self.palette["focus"] if focused
                else self.palette["normal"]
            )

            max_y, max_x = win.getmaxyx()
            if y < max_y and self.x < max_x:
                win.addstr(y, min(self.x, max_x - 1), self.label[: max_x - self.x - 1])

            max_value_len = max(1, self.width - (2 if editing else 1))
            display_value = self.value[:max_value_len].ljust(max_value_len)
            if editing:
                display_value += "█"
            
            field_x = self.x + len(self.label) + 1
            if y < max_y and field_x < max_x:
                safe_display = display_value[: max(0, max_x - field_x)]
                win.addstr(y, field_x, safe_display, attr)
        except curses.error:
            pass

    def add_char(self, char: str) -> bool:
        """Add character to field value with validation. Returns True if added successfully."""
        if len(self.value) >= self.width - 1:
            return False
            
        # Validation based on field type
        if self.field_type == "letters":
            if not char.isalpha():
                return False
            char_lower = char.lower()
            if char_lower in self.value.lower():
                return False  # No duplicates
            self.value += char_lower
            return True
        elif self.field_type == "required":
            if not char.isalpha():
                return False
            self.value = char.lower()  # Only one character allowed
            return True
        elif self.field_type == "minlen":
            if not char.isdigit():
                return False
            self.value += char
            return True
        else:
            # Default: allow any printable character
            self.value += char
            return True

    def backspace(self) -> None:
        """Remove last character from field value."""
        self.value = self.value[:-1]


def main(stdscr: "curses._CursesWindow") -> None:  # type: ignore[name-defined]
    curses.curs_set(1)
    stdscr.keypad(True)       # interpret arrow & function keys correctly
    stdscr.nodelay(False)     # blocking I/O is fine for this simple UI
    stdscr.keypad(True)       # decode function keys like PageUp
    curses.mousemask(0)       # ignore mouse/track-pad scroll events
    stdscr.clear()
    palette = init_colors()

    # Prompt user for startup values
    letters_default, required_default, min_len_default = prompt_initial_params(stdscr)

    # Build the three editable fields
    fields: list[Field] = [
        Field("Letters:", 0, 10, letters_default, "letters", palette),
        Field("Required:", 20, 2, required_default, "required", palette),
        Field("MinLen:", 35, 3, str(min_len_default), "minlen", palette),
    ]

    active = 0  # index of the currently-focused field
    editing = False  # whether we're in text editing mode
    results: list[str] = []
    offset = 0  # vertical scroll offset for results list

    def draw() -> None:
        try:
            stdscr.erase()
            h, w = stdscr.getmaxyx()

            # Help bar
            help_text = HELP_BAR.format(
                letters=len(fields[0].value),
                required=(fields[1].value or "-"),
                min_len=(fields[2].value or "-"),
            )
            if w > 0:
                stdscr.addstr(0, 0, help_text[:w], palette["help"])
                if editing:
                    badge = "  [EDITING - Esc to exit]"
                    if len(help_text) + len(badge) < w:
                        stdscr.addstr(0, len(help_text), badge, palette["editing"])

            # Input line
            for idx, f in enumerate(fields):
                f.render(stdscr, 2, focused=(idx == active), editing=(idx == active and editing))

            # Results
            start_row = 4
            available_rows = h - 5  # 0-based index 4 is first result line

            if results:
                header = f"{len(results)} candidates found"
                if h > start_row - 1:
                    stdscr.addstr(start_row - 1, 0, header, palette["header"])

            for i in range(available_rows):
                if offset + i >= len(results):
                    break
                word = results[offset + i]
                attr = (getattr(curses, "A_ITALIC", curses.A_UNDERLINE)
                        if is_pangram(word, set(fields[0].value.lower()))
                        else curses.A_NORMAL)
                stdscr.addstr(start_row + i, 2, word, attr)

            if available_rows > 0 and w > 5:
                if offset > 0 and h > start_row:
                    stdscr.addstr(start_row, w - 5, "↑", palette["bold"])
                if offset + available_rows < len(results) and h > start_row + available_rows - 1:
                    stdscr.addstr(start_row + available_rows - 1, w - 5, "↓", palette["bold"])

            stdscr.refresh()
        except curses.error:
            pass

    def run_filter() -> None:
        nonlocal results, offset
        try:
            letters = set(fields[0].value.lower())
            required = fields[1].value[:1].lower()
            min_len = int(fields[2].value or "0")
        except ValueError:
            # Non-numeric min length: treat as 0
            min_len = 0
        results = filter_words(WORDS, letters, required, min_len)
        offset = 0

    # Initial run & draw
    run_filter()
    draw()

    while True:
        key = stdscr.getch()

        # Key-dispatch loop using structural pattern matching
        match key:
            case KEYS.Q if not editing:  # q only quits when not editing
                break
            case 27:  # Esc
                if editing:
                    editing = False
                else:
                    break  # Quit if not editing
            case 9 if not editing:  # Tab - only works when not editing
                active = (active + 1) % len(fields)
            case 32 if not editing:  # Space - enter/exit edit mode
                editing = True
            case curses.KEY_UP | KEYS.K if not editing:  # Navigation only when not editing
                offset = max(0, offset - 1)
            case curses.KEY_DOWN | KEYS.J if not editing:
                offset = min(max(0, len(results) - 1), offset + 1)
            # PageUp / PageDown and scroll-wheel equivalents
            case curses.KEY_PPAGE | curses.KEY_SR if not editing:  # PageUp / scroll-up
                page = (stdscr.getmaxyx()[0] - 5) or 1
                offset = max(0, offset - page)
            case curses.KEY_NPAGE | curses.KEY_SF if not editing:  # PageDown / scroll-down
                page = (stdscr.getmaxyx()[0] - 5) or 1
                offset = min(max(0, len(results) - 1), offset + page)
            case curses.KEY_ENTER | 10 | 13:
                if editing:
                    editing = False  # Exit edit mode on Enter
                else:
                    run_filter()  # Run filter when not editing
            case key_print if 32 <= key_print < 127 and editing:  # printable ASCII - only when editing
                fld = fields[active]
                fld.add_char(chr(key_print))
            case curses.KEY_BACKSPACE | 127 if editing:  # Backspace - only when editing
                fld = fields[active]
                fld.backspace()
            case _:
                # Ignore all other keys (including mouse events when mousemask=0)
                pass

        draw()  # Redraw after every key to show state changes


if __name__ == "__main__":
    curses.wrapper(main)
